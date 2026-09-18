/*
 * Mininet lab configuration (C)
 *
 * Edit the tables below. The program prints the configuration as
 * JSON; mn-config compiles it with gcc and reads that output.
 *
 *   mn-config validate lab.c      check it (no root needed)
 *   sudo mn-config run lab.c      start the network and open the CLI
 *
 * [EDIT] change freely   [ADVANCED] only if you know why   [FIXED] don't
 * Reference: docs/configuration.md
 */

#include <stdio.h>

/* [EDIT] Lab name */
static const char *NAME = "two-switch-lab";

/* [EDIT] default | remote | none */
static const char *CONTROLLER = "default";
/* [EDIT] ovs | ovsbr | lxbr | user */
static const char *SWITCH = "ovs";
/* [ADVANCED] auto | kernel | user */
static const char *DATAPATH = "auto";

/* [EDIT] Hosts: name and address/prefix */
static const char *HOSTS[][2] = {
    { "h1", "10.0.0.1/24" },
    { "h2", "10.0.0.2/24" },
    { "h3", "10.0.0.3/24" },
};

/* [EDIT] Switches: names must contain a number */
static const char *SWITCHES[] = { "s1", "s2" };

/* [EDIT] Links: from, to, bandwidth in Mbit/s (0 = unlimited),
   delay ("" = none) */
struct link { const char *from, *to; double bw; const char *delay; };
static const struct link LINKS[] = {
    { "h1", "s1", 0, "" },
    { "h2", "s1", 0, "" },
    { "h3", "s2", 0, "" },
    { "s1", "s2", 10, "5ms" },
};

/* [EDIT] Commands to run after start, and tests (pingall, iperf) */
static const char *RUN[] = { "h1 ip -brief address" };
static const char *TESTS[] = { "pingall" };

#define COUNT(a) (sizeof(a) / sizeof((a)[0]))

/* [FIXED] Everything below prints the JSON that mn-config reads */
static void list(const char *key, const char **items, size_t n)
{
    size_t i;
    printf(",\n  \"%s\": [", key);
    for (i = 0; i < n; i++)
        printf("%s\"%s\"", i ? ", " : "", items[i]);
    printf("]");
}

int main(void)
{
    size_t i;
    printf("{\n  \"version\": 1,\n  \"name\": \"%s\",\n", NAME);
    printf("  \"network\": {\"controller\": \"%s\", \"switch\": \"%s\", "
           "\"datapath\": \"%s\"},\n", CONTROLLER, SWITCH, DATAPATH);
    printf("  \"hosts\": [");
    for (i = 0; i < COUNT(HOSTS); i++)
        printf("%s\n    {\"name\": \"%s\", \"ip\": \"%s\"}", i ? "," : "",
               HOSTS[i][0], HOSTS[i][1]);
    printf("\n  ],\n  \"switches\": [");
    for (i = 0; i < COUNT(SWITCHES); i++)
        printf("%s{\"name\": \"%s\"}", i ? ", " : "", SWITCHES[i]);
    printf("],\n  \"links\": [");
    for (i = 0; i < COUNT(LINKS); i++) {
        printf("%s\n    {\"from\": \"%s\", \"to\": \"%s\"", i ? "," : "",
               LINKS[i].from, LINKS[i].to);
        if (LINKS[i].bw > 0)
            printf(", \"bw\": %g", LINKS[i].bw);
        if (LINKS[i].delay[0])
            printf(", \"delay\": \"%s\"", LINKS[i].delay);
        printf("}");
    }
    printf("\n  ]");
    list("run", RUN, COUNT(RUN));
    list("tests", TESTS, COUNT(TESTS));
    printf("\n}\n");
    return 0;
}
