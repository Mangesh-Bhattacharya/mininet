*> Mininet lab configuration (COBOL, GnuCOBOL 3, free format)
*>
*> Edit the WORKING-STORAGE values. The program prints the
*> configuration as JSON; mn-config compiles it with "cobc -x -free"
*> and reads that output.
*>
*>   mn-config validate lab.cob      check it (no root needed)
*>   sudo mn-config run lab.cob      start the network and open the CLI
*>
*> [EDIT] change freely   [ADVANCED] only if you know why   [FIXED] don't
*> To add a host: add a FILLER pair, raise HOST-COUNT and OCCURS.
*> Reference: docs/configuration.md

IDENTIFICATION DIVISION.
PROGRAM-ID. LABCONFIG.

DATA DIVISION.
WORKING-STORAGE SECTION.
*> [EDIT] Your lab
01 LAB-NAME      PIC X(30) VALUE "two-switch-lab".
*> [EDIT] default | remote | none
01 CONTROLLER    PIC X(10) VALUE "default".
*> [EDIT] ovs | ovsbr | lxbr | user
01 SWITCH-TYPE   PIC X(10) VALUE "ovs".
*> [ADVANCED] auto | kernel | user
01 DATAPATH      PIC X(10) VALUE "auto".

*> [EDIT] Hosts: name, address/prefix
01 HOST-COUNT    PIC 99 VALUE 3.
01 HOST-VALUES.
   05 FILLER PIC X(10) VALUE "h1".
   05 FILLER PIC X(18) VALUE "10.0.0.1/24".
   05 FILLER PIC X(10) VALUE "h2".
   05 FILLER PIC X(18) VALUE "10.0.0.2/24".
   05 FILLER PIC X(10) VALUE "h3".
   05 FILLER PIC X(18) VALUE "10.0.0.3/24".
01 HOST-TABLE REDEFINES HOST-VALUES.
   05 HOST-ENTRY OCCURS 3 TIMES.
      10 HOST-NAME PIC X(10).
      10 HOST-IP   PIC X(18).

*> [EDIT] Switches: names must contain a number
01 SWITCH-COUNT  PIC 99 VALUE 2.
01 SWITCH-VALUES.
   05 FILLER PIC X(10) VALUE "s1".
   05 FILLER PIC X(10) VALUE "s2".
01 SWITCH-TABLE REDEFINES SWITCH-VALUES.
   05 SWITCH-NAME PIC X(10) OCCURS 2 TIMES.

*> [EDIT] Links: from, to, bandwidth in Mbit/s (0 = unlimited),
*> delay (spaces = none)
01 LINK-COUNT    PIC 99 VALUE 4.
01 LINK-VALUES.
   05 FILLER PIC X(10) VALUE "h1".
   05 FILLER PIC X(10) VALUE "s1".
   05 FILLER PIC 9(4)  VALUE 0.
   05 FILLER PIC X(8)  VALUE SPACES.
   05 FILLER PIC X(10) VALUE "h2".
   05 FILLER PIC X(10) VALUE "s1".
   05 FILLER PIC 9(4)  VALUE 0.
   05 FILLER PIC X(8)  VALUE SPACES.
   05 FILLER PIC X(10) VALUE "h3".
   05 FILLER PIC X(10) VALUE "s2".
   05 FILLER PIC 9(4)  VALUE 0.
   05 FILLER PIC X(8)  VALUE SPACES.
   05 FILLER PIC X(10) VALUE "s1".
   05 FILLER PIC X(10) VALUE "s2".
   05 FILLER PIC 9(4)  VALUE 10.
   05 FILLER PIC X(8)  VALUE "5ms".
01 LINK-TABLE REDEFINES LINK-VALUES.
   05 LINK-ENTRY OCCURS 4 TIMES.
      10 LINK-FROM  PIC X(10).
      10 LINK-TO    PIC X(10).
      10 LINK-BW    PIC 9(4).
      10 LINK-DELAY PIC X(8).

*> [EDIT] A command to run after start, and a test (pingall | iperf)
01 RUN-COMMAND   PIC X(60) VALUE "h1 ip -brief address".
01 TEST-NAME     PIC X(10) VALUE "pingall".

*> [FIXED] Work fields
01 I             PIC 99.
01 BW-TEXT       PIC ZZZ9.

PROCEDURE DIVISION.
*> [FIXED] Print the JSON that mn-config reads
    DISPLAY '{"version": 1, "name": "' FUNCTION TRIM(LAB-NAME) '",'
    DISPLAY ' "network": {"controller": "' FUNCTION TRIM(CONTROLLER)
            '", "switch": "' FUNCTION TRIM(SWITCH-TYPE)
            '", "datapath": "' FUNCTION TRIM(DATAPATH) '"},'

    DISPLAY ' "hosts": [' WITH NO ADVANCING
    PERFORM VARYING I FROM 1 BY 1 UNTIL I > HOST-COUNT
        IF I > 1
            DISPLAY ', ' WITH NO ADVANCING
        END-IF
        DISPLAY '{"name": "' FUNCTION TRIM(HOST-NAME(I))
                '", "ip": "' FUNCTION TRIM(HOST-IP(I)) '"}'
                WITH NO ADVANCING
    END-PERFORM
    DISPLAY '],'

    DISPLAY ' "switches": [' WITH NO ADVANCING
    PERFORM VARYING I FROM 1 BY 1 UNTIL I > SWITCH-COUNT
        IF I > 1
            DISPLAY ', ' WITH NO ADVANCING
        END-IF
        DISPLAY '{"name": "' FUNCTION TRIM(SWITCH-NAME(I)) '"}'
                WITH NO ADVANCING
    END-PERFORM
    DISPLAY '],'

    DISPLAY ' "links": [' WITH NO ADVANCING
    PERFORM VARYING I FROM 1 BY 1 UNTIL I > LINK-COUNT
        IF I > 1
            DISPLAY ', ' WITH NO ADVANCING
        END-IF
        DISPLAY '{"from": "' FUNCTION TRIM(LINK-FROM(I))
                '", "to": "' FUNCTION TRIM(LINK-TO(I)) '"'
                WITH NO ADVANCING
        IF LINK-BW(I) > 0
            MOVE LINK-BW(I) TO BW-TEXT
            DISPLAY ', "bw": ' FUNCTION TRIM(BW-TEXT) WITH NO ADVANCING
        END-IF
        IF LINK-DELAY(I) NOT = SPACES
            DISPLAY ', "delay": "' FUNCTION TRIM(LINK-DELAY(I)) '"'
                    WITH NO ADVANCING
        END-IF
        DISPLAY '}' WITH NO ADVANCING
    END-PERFORM
    DISPLAY '],'

    DISPLAY ' "run": ["' FUNCTION TRIM(RUN-COMMAND) '"],'
    DISPLAY ' "tests": ["' FUNCTION TRIM(TEST-NAME) '"]}'
    STOP RUN.
