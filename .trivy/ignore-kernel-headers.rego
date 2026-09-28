# Trivy ignore policy for the image scan gate (see SECURITY.md).
#
# linux-libc-dev ships only the kernel *headers* needed to compile C
# programs (mnexec, and C/C++ lab configurations). A container has no
# kernel of its own - Mininet uses the host's - so kernel CVEs reported
# against this package cannot be exploited inside the image; they are
# fixed by patching the host kernel. Everything else still fails the
# build, and the full scan (including these) is uploaded to the
# repository's Security tab.
package trivy

default ignore = false

ignore {
	input.PkgName == "linux-libc-dev"
}