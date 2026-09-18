// Mininet lab configuration (Java 11 or later)
//
// Edit the values in main(). The program prints the configuration as
// JSON; mn-config runs it with "java Lab.java" and reads that output.
//
//   mn-config validate Lab.java      check it (no root needed)
//   sudo mn-config run Lab.java      start the network and open the CLI
//
// [EDIT] change freely   [ADVANCED] only if you know why   [FIXED] don't
// Reference: docs/configuration.md

import java.util.ArrayList;
import java.util.List;

public class Lab {

    public static void main(String[] args) {
        // [EDIT] Your lab
        String name = "two-switch-lab";
        String controller = "default";   // default | remote | none
        String switchType = "ovs";       // ovs | ovsbr | lxbr | user
        String datapath = "auto";        // [ADVANCED] auto | kernel | user

        List<String> hosts = List.of(
            host("h1", "10.0.0.1/24"),
            host("h2", "10.0.0.2/24"),
            host("h3", "10.0.0.3/24"));
        List<String> switches = List.of(named("s1"), named("s2"));
        List<String> links = List.of(
            link("h1", "s1", 0, ""),
            link("h2", "s1", 0, ""),
            link("h3", "s2", 0, ""),
            link("s1", "s2", 10, "5ms"));    // 10 Mbit/s, 5 ms delay
        List<String> run = List.of(quote("h1 ip -brief address"));
        List<String> tests = List.of(quote("pingall"));  // pingall | iperf

        // [FIXED] Print the JSON that mn-config reads
        System.out.println("{\n  \"version\": 1,"
            + "\n  \"name\": " + quote(name) + ","
            + "\n  \"network\": {\"controller\": " + quote(controller)
            + ", \"switch\": " + quote(switchType)
            + ", \"datapath\": " + quote(datapath) + "},"
            + "\n  \"hosts\": " + array(hosts) + ","
            + "\n  \"switches\": " + array(switches) + ","
            + "\n  \"links\": " + array(links) + ","
            + "\n  \"run\": " + array(run) + ","
            + "\n  \"tests\": " + array(tests) + "\n}");
    }

    // [FIXED] JSON helpers
    static String quote(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    static String host(String name, String ip) {
        return "{\"name\": " + quote(name) + ", \"ip\": " + quote(ip) + "}";
    }

    static String named(String name) {
        return "{\"name\": " + quote(name) + "}";
    }

    static String link(String from, String to, double bw, String delay) {
        List<String> fields = new ArrayList<>();
        fields.add("\"from\": " + quote(from));
        fields.add("\"to\": " + quote(to));
        if (bw > 0) fields.add("\"bw\": " + bw);
        if (!delay.isEmpty()) fields.add("\"delay\": " + quote(delay));
        return "{" + String.join(", ", fields) + "}";
    }

    static String array(List<String> items) {
        return "[" + String.join(", ", items) + "]";
    }
}
