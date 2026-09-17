# Mininet-AI: can AI be built on, integrated with and tested in Mininet?

*Feasibility research, September 2026.*

## Summary

**Yes, with one design rule: put the AI around Mininet, not inside it.**
Mininet's core job is to emulate a network faithfully. AI adds value in
three places around it:

1. **In the control plane**: ML or reinforcement-learning logic inside an
   SDN controller (routing, DDoS detection, traffic classification).
2. **As an operator**: LLM agents that configure, troubleshoot and
   explain the network through a safe tool interface.
3. **As a teacher**: an assistant that diagnoses a student's setup,
   explains failures and generates and grades labs.

All three are feasible now, and parts of each have already been
demonstrated in published research, mostly with other emulators. The gap
Mininet-AI can fill is an **open, reproducible, cross-platform
Mininet/OpenFlow environment with a standard agent interface (MCP and
Gymnasium) and a scored scenario benchmark**. Current LLM network
benchmarks are built on Kathará containers, not on the OpenFlow/Mininet
stack that most SDN courses teach.

The cross-platform work in this fork is the prerequisite, and it's done:
Mininet now runs the same way in a privileged container on amd64 and
arm64, on native Ubuntu/Debian, in WSL 2 and in VMs; CI brings up real
networks on every change; and `mn-doctor --json` already gives agents a
machine-readable view of the environment.

---

## 1. Why Mininet suits AI work

| Property | Why it matters for AI |
|----------|-----------------------|
| Real Linux network stack (namespaces, veth, OVS) | Agents and models see real packets, real `ping`/`iperf`/`tcpdump` output and real OpenFlow tables, not a simulator's abstraction |
| Python API | Topologies, faults and measurements can be scripted, so they are reproducible and usable as environments or tools |
| OpenFlow / Open vSwitch | Control-plane decisions (flow rules) are explicit and inspectable, a natural action space for RL and a verifiable output for LLMs |
| Cheap to reset | A network starts in seconds, so experiments can run thousands of episodes or scenarios |
| Container-friendly (this fork) | A privileged container is a clear blast-radius boundary for an agent that runs commands as root |
| Teaching adoption | Many SDN courses and tutorials already use Mininet, so an AI layer reaches students where they are |

**Limits to design around:**
- **No time dilation.** Mininet shares one machine's CPU, so heavy
  traffic or many nodes distort latency and throughput. AI experiments
  should use functional metrics (reachability, correct rules, detection
  accuracy) or be sized so the host isn't saturated.
- **Scale.** Hundreds of nodes on a laptop, not tens of thousands.
- **Userspace datapath.** On Docker Desktop the OVS userspace datapath
  keeps things working but is slower, so throughput-based rewards or
  features will differ from native Linux.
- **Controllers.** Ryu, the classic Python controller in coursework, is no
  longer maintained. Its OpenStack fork **OS-Ken** is the maintained
  option; POX and ONOS/OpenDaylight are alternatives.

## 2. Prior art

| Work | What it shows | Emulator | Relevance |
|------|---------------|----------|-----------|
| **MininetGym** (SoftwareX; `dipi-unimore/mininet-gym`) | Gymnasium environments on Mininet + OpenDaylight for traffic classification and DoS detection; Q-learning, SARSA, DQN, PPO, A2C, plus multi-agent (PettingZoo) | Mininet | RL on Mininet works; confirms the Gym pattern |
| **sdn-marl** (`heysan1405/sdn-marl`) | Multi-agent RL routing baseline with Topology Zoo loader and monitoring | Mininet | Routing-focused RL on Mininet |
| **InSDN** and later SDN IDS datasets | Labelled SDN attack traffic, including control-plane features | SDN testbeds | Training data and feature design for ML detectors |
| **"Trust, But Verify"** (Soares et al., arXiv 2510.20703, 2025) | ChatGPT, Copilot, DeepSeek and BlackBox.ai generated POX controllers for three tasks, tested in Mininet. All tools could produce functional controllers; ChatGPT and DeepSeek were more consistent, the others needed more fixes | Mininet + POX | LLM output must be verified by emulation, which Mininet-AI automates |
| **NetConfEval** (CoNEXT 2024 / PACMNET) | Benchmarks LLMs translating natural-language requirements into network configuration and code | Kathará (FRR: OSPF, RIP, BGP) | Methodology for scoring LLM config generation |
| **NIKA** (Wang et al., arXiv 2512.16381, 2025) | 640 incidents across 54 issue types and 5 scenarios, agents use 30+ tools over **MCP**. GPT-5 reached 89% detection, 68.7% localization, 55.3% root-cause accuracy; smaller models far lower | Kathará | Closest template for an agent benchmark; shows root-cause analysis is still hard |
| **Confucius** (Meta, SIGCOMM 2025) | Production multi-agent LLM framework for intent-driven network management, operating for two years with 60+ applications | Production | LLM network agents are viable at scale when paired with validation |
| **Intent-based networking prototypes** (e.g. `YannickWend/intent-based-networking`) | Natural-language intent → policy → Ryu/OpenFlow rules on Mininet | Mininet | End-to-end LLM → OpenFlow is buildable on Mininet |

**Gap:** RL-on-Mininet environments exist, and LLM-agent benchmarks exist,
but not together. No maintained project offers Mininet/OpenFlow scenarios
with fault injection, a standard agent interface (MCP for LLMs, Gymnasium
for RL) and deterministic scoring that runs identically on a student
laptop and in CI.

## 3. Proposed architecture

```
+----------------------------------------------------------------------+
|  Agents (pluggable)                                                  |
|  rule-based baseline | ML detector | RL policy | LLM agent (via MCP) |
+-------------------------------+--------------------------------------+
                                | typed, allow-listed actions (JSON)
+-------------------------------v--------------------------------------+
|  mininet_ai interface layer                                          |
|  - Gymnasium env (observations = stats/flows, actions = flow rules)  |
|  - MCP server (tools: get_topology, ping, iperf, dump_flows,         |
|    add_flow, set_link, get_logs, ...)                                |
|  - Scenario runner: build topology -> inject fault -> run agent ->   |
|    verify -> score                                                   |
+-------------------------------+--------------------------------------+
                                | Mininet Python API, ovs-ofctl
+-------------------------------v--------------------------------------+
|  Environment: this Mininet fork in a privileged container or VM      |
|  topologies as code, fault injectors (link down, loss, controller    |
|  crash, bad flow rule, DoS traffic), telemetry (port/flow stats)     |
+----------------------------------------------------------------------+
```

### Design principles
1. **Typed tools, not a root shell.** Agents call narrow actions with
   validated parameters that return JSON. A raw `host_cmd` tool, if
   offered at all, is off by default and confined to Mininet hosts.
2. **The container is the sandbox.** Everything runs inside the Docker
   image from this fork (or a VM), never with root on a student's host.
3. **Verify, don't trust.** Every scenario has a ground-truth checker
   (reachability matrix, expected flow rules, recovered throughput) that
   is independent of what the agent claims.
4. **Network data is untrusted input.** Hostnames, packet payloads, logs
   and web pages served inside the emulated network can carry prompt
   injection. The agent's instructions come only from the scenario
   definition.
5. **Model-agnostic.** MCP and Gymnasium keep agents swappable (Claude,
   other hosted or local LLMs, SB3 policies, classic baselines).
6. **Separate repository.** Build `mininet-ai` as its own package that
   depends on this fork, so the fork stays upstream-compatible.

## 4. How it can be tested

| Level | What | Runs where | Needs root / API keys |
|-------|------|------------|------------------------|
| Unit | Action validation, observation parsing, scoring logic against fake environments (the same pattern as `mininet/test/test_doctor.py`) | anywhere, every commit | no / no |
| Integration | Each tool against a real Mininet network: `add_flow` changes reachability, `set_link` changes loss | GitHub Actions Linux runners, Docker image (proven by this fork's CI) | yes (in CI) / no |
| Scenario regression | Fixed scenarios × seeds with a **scripted baseline agent** and **recorded LLM transcripts** replayed deterministically | CI | yes / no |
| Live benchmark | Real LLMs / trained RL policies on the full scenario set; results tracked over time | scheduled or manual workflow with secrets | yes / yes |
| Human study | Students using the tutor: time to fix a broken setup, lab completion, quiz scores | course pilot | n/a |

**Metrics**
- *Operations agents:* detection / localization / root-cause accuracy,
  fix success rate (verified by the checker), time and tool calls to
  resolution, tokens and cost, harmful-action rate (actions that made the
  network worse), and false fixes (claimed fixed but checker fails).
- *ML/RL:* precision/recall/F1 for detection, reward and convergence,
  generalization to unseen topologies, stability across seeds.
- *Tutor:* correctness of diagnoses against `mn-doctor` ground truth and
  student outcomes.

Baselines matter: every AI result should be compared with a simple
rule-based agent on the same scenarios.

## 5. Feasibility assessment

| Capability | Feasibility | Evidence | Main risk |
|------------|-------------|----------|-----------|
| Cross-platform, reproducible environment | **Done** | This fork's CI: native Ubuntu, Debian containers, Docker amd64/arm64 | Docker Desktop kernel features (tc qdiscs) vary; `mn-doctor` reports them |
| Tool/MCP interface for LLM agents | **High** | NIKA uses MCP over an emulator; the Mininet Python API maps directly to tools | Designing a safe action set |
| LLM troubleshooting and configuration agent | **High for detection, medium for root cause** | NIKA: strong detection, much lower RCA even for top models | Nondeterminism, cost, overconfident "fixes" (mitigated by checkers) |
| LLM-generated controller code verified in Mininet | **High** | "Trust, But Verify" did this manually; can be automated | Code needs sandboxed execution |
| ML intrusion/DDoS detection on live Mininet traffic | **High** | Many Mininet + controller + ML studies; InSDN-style features | Emulated traffic can be less diverse than real traffic |
| RL routing / mitigation (Gym env) | **Medium-high** | MininetGym, sdn-marl | Slow wall-clock episodes; sim-to-real gap |
| AI tutor for students | **High** | `mn-doctor --json` + CLI transcripts give grounded context | Must not give wrong fixes confidently; keep it grounded in checks |

## 6. Roadmap

| Phase | Deliverable | Test gate |
|-------|-------------|-----------|
| **0 (done)** | Cross-platform Mininet, Docker image, CI, `mn-doctor --json` | Workflows green on every commit |
| **1** | `mininet-ai` package: typed action API, 5 fault-injection scenarios, deterministic checkers, rule-based baseline | Unit tests without root; integration tests in the fork's Docker image in CI |
| **2** | MCP server + LLM troubleshooting agent; 20-50 scenario benchmark with detection/localization/fix scoring | Recorded-transcript replay in CI; manual live runs with an API key |
| **3** | Gymnasium environment + ML DDoS detector (can reuse ideas from the `graph-based-network-intrusion-detection` project) + RL mitigation demo | Seeded training runs meet a baseline F1/reward; reproducible across two platforms |
| **4** | Student tutor: explains `mn-doctor` results and CLI errors, generates and autogrades labs | Accuracy on a labelled set of broken setups; small course pilot |

## 7. Decisions needed before building

1. **Starting point:** LLM operations agent (phases 1-2, most novel,
   benchmark-worthy) or ML/RL security (phase 3, strongest link to
   existing IDS work)? Recommendation: phases 1-2 first. The action API
   and scenarios they create are reused by the RL environment and the
   tutor.
2. **Models:** default to Claude for the reference agent while keeping
   the MCP interface model-agnostic, and include one open-weights model
   for a no-cost student option.
3. **Controller:** OS-Ken (maintained Ryu fork) as the Python controller
   for AI-in-the-control-plane work, with POX kept for existing course
   material.

## Sources

- MininetGym: [GitHub](https://github.com/dipi-unimore/mininet-gym),
  [SoftwareX article](https://www.sciencedirect.com/science/article/pii/S235271102500278X)
- [sdn-marl](https://github.com/heysan1405/sdn-marl)
- [InSDN: A Novel SDN Intrusion Dataset](https://www.researchgate.net/publication/344206268_InSDN_A_Novel_SDN_Intrusion_Dataset)
- [Trust, But Verify: An Empirical Evaluation of AI-Generated Code for SDN Controllers](https://arxiv.org/pdf/2510.20703)
- NetConfEval: [paper](https://dl.acm.org/doi/10.1145/3656296),
  [code](https://github.com/RedHatResearch/conext24-NetConfEval)
- [NIKA: A Network Arena for Benchmarking AI Agents on Network Troubleshooting](https://arxiv.org/html/2512.16381v1)
- [Intent-Driven Network Management with Multi-Agent LLMs: The Confucius Framework](https://dl.acm.org/doi/10.1145/3718958.3750537)
- [Intent-based networking prototype (Mininet, Ryu, LLM)](https://github.com/YannickWend/intent-based-networking)
- [Ryu (points to OS-Ken as the maintained fork)](https://github.com/faucetsdn/ryu)
- [IETF draft: A Framework to Evaluate LLM Agents for Network Configuration](https://datatracker.ietf.org/doc/draft-cui-nmrg-llm-benchmark/)
