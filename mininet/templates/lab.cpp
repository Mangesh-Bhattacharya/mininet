// Mininet lab configuration (C++17)
//
// Edit the values in main(). The program prints the configuration as
// JSON; mn-config compiles it with g++ and reads that output.
//
//   mn-config validate lab.cpp      check it (no root needed)
//   sudo mn-config run lab.cpp      start the network and open the CLI
//
// [EDIT] change freely   [ADVANCED] only if you know why   [FIXED] don't
// Reference: docs/configuration.md

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

struct Host { std::string name, ip; };
struct Link { std::string from, to; double bw = 0; std::string delay; };

// [FIXED] JSON helpers
static std::string quote(const std::string &s) { return "\"" + s + "\""; }

template <typename T, typename F>
static std::string array(const std::vector<T> &items, F toJson)
{
    std::ostringstream out;
    out << "[";
    for (size_t i = 0; i < items.size(); ++i)
        out << (i ? ", " : "") << toJson(items[i]);
    out << "]";
    return out.str();
}

int main()
{
    // [EDIT] Your lab
    const std::string name = "two-switch-lab";
    const std::string controller = "default";  // default | remote | none
    const std::string switchType = "ovs";      // ovs | ovsbr | lxbr | user
    const std::string datapath = "auto";       // [ADVANCED] auto|kernel|user

    const std::vector<Host> hosts = {
        {"h1", "10.0.0.1/24"}, {"h2", "10.0.0.2/24"}, {"h3", "10.0.0.3/24"},
    };
    const std::vector<std::string> switches = {"s1", "s2"};
    const std::vector<Link> links = {
        {"h1", "s1"}, {"h2", "s1"}, {"h3", "s2"},
        {"s1", "s2", 10, "5ms"},  // 10 Mbit/s, 5 ms delay
    };
    const std::vector<std::string> run = {"h1 ip -brief address"};
    const std::vector<std::string> tests = {"pingall"};  // pingall | iperf

    // [FIXED] Print the JSON that mn-config reads
    std::cout << "{\n  \"version\": 1,\n  \"name\": " << quote(name)
              << ",\n  \"network\": {\"controller\": " << quote(controller)
              << ", \"switch\": " << quote(switchType)
              << ", \"datapath\": " << quote(datapath) << "},\n"
              << "  \"hosts\": " << array(hosts, [](const Host &h) {
                     return "{\"name\": " + quote(h.name) +
                            ", \"ip\": " + quote(h.ip) + "}";
                 })
              << ",\n  \"switches\": " << array(switches,
                     [](const std::string &s) {
                         return "{\"name\": " + quote(s) + "}";
                     })
              << ",\n  \"links\": " << array(links, [](const Link &l) {
                     std::ostringstream o;
                     o << "{\"from\": " << quote(l.from)
                       << ", \"to\": " << quote(l.to);
                     if (l.bw > 0) o << ", \"bw\": " << l.bw;
                     if (!l.delay.empty())
                         o << ", \"delay\": " << quote(l.delay);
                     o << "}";
                     return o.str();
                 })
              << ",\n  \"run\": " << array(run, quote)
              << ",\n  \"tests\": " << array(tests, quote) << "\n}\n";
    return 0;
}
