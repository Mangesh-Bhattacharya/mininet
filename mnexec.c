/* mnexec: execution utility for mininet
 *
 * Starts up programs and does things that are slow or
 * difficult in Python, including:
 *
 *  - closing all file descriptors except stdin/out/error
 *  - detaching from a controlling tty using setsid
 *  - running in network and mount namespaces
 *  - printing out the pid of a process so we can identify it later
 *  - attaching to a namespace and cgroup
 *  - setting RT scheduling
 *
 * Partially based on public domain setsid(1)
*/

#define _GNU_SOURCE
#include <stdio.h>
#include <linux/sched.h>
#include <unistd.h>
#include <limits.h>
#include <syscall.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sched.h>
#include <ctype.h>
#include <sys/mount.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <dirent.h>
#include <errno.h>

#if !defined(VERSION)
#define VERSION "(devel)"
#endif

void usage(char *name)
{
    printf("Execution utility for Mininet\n\n"
           "Usage: %s [-cdnp] [-a pid] [-g group] [-r rtprio] cmd args...\n\n"
           "Options:\n"
           "  -c: close all file descriptors except stdin/out/error\n"
           "  -d: detach from tty by calling setsid()\n"
           "  -n: run in new network and mount namespaces\n"
           "  -p: print ^A + pid\n"
           "  -a pid: attach to pid's network and mount namespaces\n"
           "  -g group: add to cgroup\n"
           "  -r rtprio: run with SCHED_RR (usually requires -g)\n"
           "  -v: print version\n",
           name);
}


int setns(int fd, int nstype)
{
    return syscall(__NR_setns, fd, nstype);
}

/* Validate alphanumeric path foo1/bar2/baz */
void validate(char *path)
{
    char *s;
    for (s=path; *s; s++) {
        /* isalnum() needs an unsigned char value */
        if (!isalnum((unsigned char)*s) && *s != '/') {
            fprintf(stderr, "invalid path: %s\n", path);
            exit(1);
        }
    }
}

/* Write pid to an existing file (never creates one); 1 on success */
int writepid(const char *path, pid_t pid)
{
    int ok;
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0)
        return 0;
    ok = dprintf(fd, "%d\n", pid) > 0;
    close(fd);
    return ok;
}

/* Add our pid to cgroup */
void cgroup(char *gname)
{
    static char path[PATH_MAX];
    static char *groups[] = {
        "cpu", "cpuacct", "cpuset", NULL
    };
    char **gptr;
    pid_t pid = getpid();
    int count = 0;
    validate(gname);
    for (gptr = groups; *gptr; gptr++) {
        snprintf(path, PATH_MAX, "/sys/fs/cgroup/%s/%s/tasks",
                 *gptr, gname);
        count += writepid(path, pid);
    }
    if (!count) {
        /* cgroup v2 (unified hierarchy, the default on current Linux
           distributions): one group directory with a cgroup.procs file */
        snprintf(path, PATH_MAX, "/sys/fs/cgroup/%s/cgroup.procs", gname);
        count += writepid(path, pid);
    }
    if (!count) {
        fprintf(stderr, "cgroup: could not add to cgroup %s\n",
            gname);
        exit(1);
    }
}

/* Parse a positive pid, or exit with an error */
pid_t parsepid(const char *arg)
{
    char *end;
    long value;
    errno = 0;
    value = strtol(arg, &end, 10);
    if (errno || end == arg || *end || value <= 0 || value > INT_MAX) {
        fprintf(stderr, "invalid pid: %s\n", arg);
        exit(1);
    }
    return (pid_t)value;
}

int main(int argc, char *argv[])
{
    int c;
    int fd;
    DIR *dir;
    struct dirent *de;
    char path[PATH_MAX];
    int nsid;
    int pid;
    char *cwd = get_current_dir_name();
    static struct sched_param sp;

    while ((c = getopt(argc, argv, "+cdnpa:g:r:vh")) != -1)
        switch(c) {
        case 'c':
            /* close file descriptors except stdin/out/error */
            if ((dir = opendir("/proc/self/fd"))) {
                /* don't close the directory we are reading */
                int dirfd_ = dirfd(dir);
                while ((de = readdir(dir)))
                    if ((fd = atoi(de->d_name)) > 2 && fd != dirfd_)
                        close(fd);
                closedir(dir);
            }
            /* fall back to old method if needed */
            else for (fd = getdtablesize(); fd > 2; fd--)
                     close(fd);
            break;
        case 'd':
            /* detach from tty */
            if (getpgrp() == getpid()) {
                switch(fork()) {
                    case -1:
                        perror("fork");
                        return 1;
                    case 0:     /* child */
                        break;
                    default:    /* parent */
                        return 0;
                }
            }
            setsid();
            break;
        case 'n':
            /* run in network and mount namespaces */
            if (unshare(CLONE_NEWNET|CLONE_NEWNS) == -1) {
                perror("unshare");
                return 1;
            }

            /* Mark our whole hierarchy recursively as private, so that our
             * mounts do not propagate to other processes.
             */

            if (mount("none", "/", NULL, MS_REC|MS_PRIVATE, NULL) == -1) {
                perror("remount");
                return 1;
            }

            /* mount sysfs to pick up the new network namespace */
            if (mount("sysfs", "/sys", "sysfs", MS_MGC_VAL, NULL) == -1) {
                perror("mount");
                return 1;
            }
            break;
        case 'p':
            /* print pid */
            printf("\001%d\n", getpid());
            fflush(stdout);
            break;
        case 'a':
            /* Attach to pid's network namespace and mount namespace */
            pid = parsepid(optarg);
            snprintf(path, sizeof(path), "/proc/%d/ns/net", pid);
            /* O_CLOEXEC: don't leak namespace fds into the command */
            nsid = open(path, O_RDONLY | O_CLOEXEC);
            if (nsid < 0) {
                perror(path);
                return 1;
            }
            if (setns(nsid, 0) != 0) {
                perror("setns");
                return 1;
            }
            close(nsid);
            /* Plan A: call setns() to attach to mount namespace */
            snprintf(path, sizeof(path), "/proc/%d/ns/mnt", pid);
            nsid = open(path, O_RDONLY | O_CLOEXEC);
            if (nsid < 0 || setns(nsid, 0) != 0) {
                /* Plan B: chroot/chdir into pid's root file system */
                snprintf(path, sizeof(path), "/proc/%d/root", pid);
                if (chroot(path) < 0) {
                    perror(path);
                    return 1;
                }
            }
            if (nsid >= 0)
                close(nsid);
            /* chdir to correct working directory */
            if (!cwd) {
                perror("getcwd");
                return 1;
            }
            if (chdir(cwd) != 0) {
                perror(cwd);
                return 1;
            }
            break;
        case 'g':
            /* Attach to cgroup */
            cgroup(optarg);
            break;
        case 'r':
            /* Set RT scheduling priority */
            sp.sched_priority = atoi(optarg);
            if (sched_setscheduler(getpid(), SCHED_RR, &sp) < 0) {
                perror("sched_setscheduler");
                return 1;
            }
            break;
        case 'v':
            printf("%s\n", VERSION);
            exit(0);
        case 'h':
            usage(argv[0]);
            exit(0);
        default:
            usage(argv[0]);
            exit(1);
        }

    if (optind < argc) {
        execvp(argv[optind], &argv[optind]);
        perror(argv[optind]);
        return 1;
    }

    usage(argv[0]);

    return 0;
}
