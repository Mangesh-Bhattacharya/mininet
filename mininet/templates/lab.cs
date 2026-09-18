// Mininet lab configuration (C#, .NET 6 or later)
//
// Edit the values below. The program prints the configuration as
// JSON; mn-config builds it with the dotnet SDK and reads that output.
//
//   mn-config validate lab.cs      check it (no root needed)
//   sudo mn-config run lab.cs      start the network and open the CLI
//
// [EDIT] change freely   [ADVANCED] only if you know why   [FIXED] don't
// Reference: docs/configuration.md

using System.Text.Json;

var config = new Dictionary<string, object>
{
    ["version"] = 1,                                  // [FIXED]
    ["name"] = "two-switch-lab",                      // [EDIT]
    ["network"] = new Dictionary<string, object>
    {
        ["controller"] = "default",   // [EDIT] default | remote | none
        ["switch"] = "ovs",           // [EDIT] ovs | ovsbr | lxbr | user
        ["datapath"] = "auto",        // [ADVANCED] auto | kernel | user
    },
    // [EDIT] Hosts: name and address/prefix
    ["hosts"] = new[]
    {
        Host("h1", "10.0.0.1/24"),
        Host("h2", "10.0.0.2/24"),
        Host("h3", "10.0.0.3/24"),
    },
    // [EDIT] Switch names must contain a number
    ["switches"] = new[] { Named("s1"), Named("s2") },
    // [EDIT] Links; the last one is 10 Mbit/s with 5 ms delay
    ["links"] = new object[]
    {
        new[] { "h1", "s1" },
        new[] { "h2", "s1" },
        new[] { "h3", "s2" },
        new Dictionary<string, object>
        {
            ["from"] = "s1", ["to"] = "s2", ["bw"] = 10, ["delay"] = "5ms",
        },
    },
    ["run"] = new[] { "h1 ip -brief address" },      // [EDIT]
    ["tests"] = new[] { "pingall" },                 // [EDIT] pingall | iperf
};

// [FIXED] Print the JSON that mn-config reads
Console.WriteLine(JsonSerializer.Serialize(config,
    new JsonSerializerOptions { WriteIndented = true }));

static Dictionary<string, object> Host(string name, string ip) =>
    new() { ["name"] = name, ["ip"] = ip };

static Dictionary<string, object> Named(string name) =>
    new() { ["name"] = name };
