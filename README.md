# Multi-Agent Smart Water Distribution with Computer Vision-Based Container Detection and AI-Driven Behavior Forecasting for Disaster Relief in Smart Cities

Code for the IEEE ICA 2025 paper. Each dispenser is an autonomous edge agent: it verifies the container (MobileNet-SSD, TFLite),
forecasts short-term demand (LSTM, TFLite), chooses `{dispense, wait, forward_request}` with a PPO-trained policy, and
coordinates with neighbours over MQTT / LoRa / NB-IoT without a cloud service.

> **Read "Status and known gaps" before citing any number from this repository.** What is implemented, what has only been
> tested against simulated peripherals, and what is *not* included is listed explicitly below.

## Repository layout

| Path | What it is |
|---|---|
| `agent/` | Edge agent: `main.py` (control loop), `hardware.py` (Table I sensors + pump), `perception.py` (camera, SSD detector, volume calibration), `forecast.py` (LSTM/TFLite + EMA fallback), `policy.py` (NumPy PPO actor), `comms.py` (MQTT, SX1278 LoRa, SIM7000 NB-IoT), `spec.py` (state/action definition), `metrics.py` |
| `sim/` | Gymnasium multi-agent simulator, baselines (heuristic, centralised), experiment runner; `connectivity.py` (broker-outage environment and ablation variants), `train_variants.py`, `run_paper_experiments.py` (v2 paper experiments) |
| `train/` | `train_ppo.py` (Stable-Baselines3 PPO -> NumPy export), `train_forecaster.py` (LSTM -> TFLite) |
| `gateway/` | `lora_gateway.py` (SX1278 -> MQTT), `firebase_bridge.py` (MQTT -> Firebase for Admin-Web) |
| `dashboard/node-red-flow.json` | Node-RED dashboard flow (Fig. 9) |
| `tools/calibrate_volume.py` | Bounding-box volume calibration with 200/500/600 ml reference containers |
| `config/agent.example.yaml` | Per-dispenser configuration (pins, link, model paths) |
| `tests/` | 56 tests (`python -m pytest`): 54 pass and 1 is an expected failure that pins a known gap; modules skip when `amqtt`, TensorFlow or `mosquitto` is missing |
| `IOT/` | ESP32-CAM sketches used **only to collect the training images** (Edge Impulse). Not the dispenser firmware. |
| `computer-vision-...-export/` | Edge Impulse dataset export (134 images) |
| `results/`, `models/ablation/` | Output of the v2 paper simulation experiments and the PPO actors it evaluates (see "Paper v2 simulation experiments"); `results/sil/` holds the software-in-the-loop runs |
| `sim/sil/`, `sim/run_sil.py`, `deploy/` | Software-in-the-loop deployment: real agents, real Mosquitto, the real gateway scripts, simulated peripherals (see "Software-in-the-loop deployment") |
| `Admin-Web/` | Angular admin dashboard (reads Firebase) |

## Paper specification -> code

| Paper | Code | Status |
|---|---|---|
| Raspberry Pi 4 / Jetson Nano agent (Table I) | `agent/main.py`, `agent/hardware.py` (RPi.GPIO / Jetson.GPIO, BCM pins) | Implemented. Logic tested with simulated hardware; **not run on a real Pi/Jetson** |
| Pi Camera v2 | `agent/perception.py::Camera` (picamera2, OpenCV fallback) | Implemented, not run on real camera |
| HC-SR04, DHT22, IR E18-D80NK | `agent/hardware.py` | Implemented, **not bench-tested**. See wiring warnings in the file (5 V echo / open-collector levels) |
| MobileNet-SSD + TFLite + bbox volume calibration | `agent/perception.py`, `tools/calibrate_volume.py` | Inference + calibration code unit-tested with a fake interpreter. **No trained model is included** (see gaps) |
| LSTM forecaster, 5-10 min horizon | `agent/forecast.py`, `train/train_forecaster.py` | Pipeline works end to end (Keras -> TFLite, max abs diff 1.5e-07). **Not validated on real data** (see gaps) |
| MARL with PPO, state `[sensors, CV flag, forecast, queue]`, actions `{dispense, wait, forward_request}` | `agent/spec.py`, `sim/env.py`, `train/train_ppo.py`, `agent/policy.py` | Implemented. One parameter-shared policy trained in simulation, executed independently per agent on local observations |
| MQTT / Mosquitto messaging | `agent/comms.py::MqttLink` | Tested end to end against a pure-Python broker (amqtt). **Re-test against Mosquitto** |
| LoRaWAN / NB-IoT (SX1278, SIM7000) | `LoraLink` + `SX1278`, `NbIotLink` | Tested only against a fake SPI register file and a scripted AT modem. **Not on hardware. LoRa here is raw point-to-point, not LoRaWAN** |
| Central dashboard (Node-RED + Firebase) | `dashboard/node-red-flow.json`, `gateway/firebase_bridge.py`, `Admin-Web/` | Flow JSON is valid but was **not imported into Node-RED**; Firebase bridge not run against a live database |
| 20-40 % packet-loss robustness | `sim/run_experiment.py` | Simulated only (see results) |

## Status and known gaps

1. **SX1278 is not LoRaWAN-capable in the AS923 band.** The chip covers 137-525 MHz only (Semtech datasheet), so `LoraLink`
   is LoRa point-to-point at 433 MHz. For LoRaWAN in Thailand (AS923, ~920-925 MHz) use an SX1276-class module and a LoRaWAN
   stack/gateway; check the local rules for 433 MHz before deploying. The paper's "LoRaWAN" wording and the SX1278 in Table I
   cannot both be true.
2. **No MobileNet-SSD model is included.** The Edge Impulse export has 134 images with two classes ("able" / "not able");
   the 200/500/600 ml classes shown in Figs. 4-8 are not in the exported labels. Volume is estimated from bounding-box area
   against reference containers (`tools/calibrate_volume.py`), which needs a trained detector and a fixed camera distance.
   `agent/main.py` refuses to dispense without a working detector unless `cv.allow_without_model: true`.
3. **Forecaster.** On synthetic data (the only data available here) the LSTM did **not** beat a simple EMA:
   held-out MAE 1.633 (LSTM) vs 1.357 (EMA) vs 1.654 (persistence), mean target 2.71 requests / 5 min. Synthetic data cannot
   say anything about real accuracy. Train on real logs (`python -m train.train_forecaster --csv usage.csv`) and compare against the EMA
   baseline before deploying; the agent falls back to the EMA when no model file is present. The demo model is therefore not shipped.
4. **Simulation results do not reproduce the paper's numbers and are not comparable to them.** See the table below.
5. **Fairness index.** The paper does not define it. `agent/metrics.py` uses Jain's index over per-request service quality
   `1 - latency/timeout` (0 for failed requests). Change `quality()` if your definition differs.
6. **Latency of forwarded requests** is measured from the original request (the waiting time travels in the Forward message),
   but one-way radio transit time is not included because agent clocks are not synchronised.
7. **`pump relay` is required but not listed in Table I** (something must implement `dispense`). Calibrate `flow_ml_per_s`.
8. **Python >= 3.8.** Table II lists Raspbian Buster, whose stock Python 3.7 is too old; use Ubuntu 20.04 or Raspberry Pi OS Bullseye+.
9. TensorFlow and PyTorch crashed when loaded in the same process in our environment; the training scripts are separate processes, and the PPO test runs in a subprocess.
10. **Where the MQTT broker runs is not recorded in this repository.** What the code and configuration say: `agent.example.yaml`
   points the agents at a broker on a LAN address (`192.168.1.10:1883`); `gateway/lora_gateway.py` and `gateway/firebase_bridge.py`
   default to `--mqtt-host localhost`; the Node-RED flow's Mosquitto node is `localhost:1883`. No Mosquitto configuration file and
   no hardware logs are included, so the repository does not show where the broker ran in the laboratory or field trials.
   With the broker unreachable (nothing listening on the port), an MQTT agent still dispenses locally; `tests/test_broker_unreachable.py`
   runs the real `MqttLink` and `Agent` against a closed port and checks this. It does not tell where the broker ran in any trial.
   With NB-IoT the behaviour is different: a modem error on `AT+SMPUB` makes `NbIotLink.send()` raise inside `Agent.step()`, before the
   dispense decision, and `Agent.run()` does not catch it, so the agent loop ends. `tests/test_known_gaps.py` pins this with the scripted
   modem in `tests/helpers.py`; it is not fixed yet. "Software-in-the-loop deployment" below re-creates a broker, gateway and dashboard
   path and measures what each one's loss does; it does not recover the original setup.
11. **A tank holding between `volume` and `volume + reserve_ml` neither dispenses nor forwards.** The heuristic policy forwards only when
    `water < volume`, while the agent's reserve guard blocks a dispense that would leave less than `reserve_ml` (200 ml). With 700 ml in
    the tank, a 600 ml container and a neighbour with water known, the agent waits until the request times out
    (`tests/test_known_gaps.py`, expected failure). The trained PPO actors were not checked for this.
12. **`gateway/lora_gateway.py` and `gateway/firebase_bridge.py` do not retry their first MQTT connection.** If the broker is not
    reachable when they start, they exit (5 of 5 software-in-the-loop runs without a broker). Once connected they reconnect on their own.
    Run them under a supervisor that restarts them (for example systemd `Restart=always`). `firebase_bridge.py` gained a `--mqtt-port` option
    (it was fixed to 1883).

### Simulation results (20 agents, 100 requests, 30 seeds, mean ± std of success rate)

Simulator assumptions (see `sim/env.py`): forecast = noisy oracle of true arrivals, CV = Bernoulli flag (92 % accuracy),
latency in *simulated* seconds, centralised baseline loses a decision cycle (3 s timeout) when either the telemetry or the
command packet is lost. PPO trained for 300k steps with packet loss sampled in [0, 40 %].

| Policy | Loss | Success % | Mean latency (s) | Jain fairness |
|---|---|---|---|---|
| heuristic (decentralised) | 0 % | 94.8 ± 4.7 | 11.9 | 0.894 |
| heuristic (decentralised) | 40 % | 94.8 ± 4.6 | 13.7 | 0.891 |
| centralised | 0 % | 95.1 ± 4.0 | 13.1 | 0.887 |
| centralised | 40 % | 83.4 ± 5.6 | 51.7 | 0.617 |
| PPO (decentralised) | 0 % | 95.6 ± 3.8 | 13.2 | 0.898 |
| PPO (decentralised) | 40 % | 95.3 ± 4.3 | 15.4 | 0.891 |

Reading: decentralised control keeps ~95 % success under 40 % loss while the centralised baseline degrades; this is
consistent with the paper's resilience argument but it follows from the baseline's assumed timeout. **PPO is
statistically indistinguishable from the rule-based heuristic here** (differences are far below one standard deviation), so
the paper's "32 % fairness improvement over a heuristic baseline" is not reproduced by this simulator. Full table:
`python -m sim.run_experiment --csv results.csv`.

The paper's hardware results (94.5 % success, 1.3 s latency, 92 % / 1.5 s / 4.7 of 5 in the field trial, 92 % detection accuracy,
18 % / 22 % improvements) come from physical trials and cannot be reproduced from this repository. Use `agent/metrics.py` on
`logs/agent-*.jsonl` from your own deployment to compute success rate, latency and fairness.

### Paper v2 simulation experiments

Everything below is **simulation**, not a measurement of the physical dispensers. It uses the same abstract model as above
(noisy-oracle forecast, Bernoulli CV flag, simulated seconds, the centralised baseline's assumed 3 s timeout).

```bash
pip install -r requirements/train.txt
# 4 PPO variants x 5 training seeds (300k steps each); one process per run, see the docstring of sim/train_variants.py
python -m sim.train_variants --variant full --seeds 0 1 2 3 4        # also: no_forecast, no_volume, no_fairness
python -m sim.run_paper_experiments --eval-seeds 30 --out results/
python -m pytest tests/test_connectivity.py
```

* Scenarios: packet loss 0 / 20 / 30 / 40 %; the broker unreachable for 100-200 s (covers the demand surge); unreachable for the whole run.
  `sim/connectivity.py::OutageEnv` forces the drop probability to 1.0 inside the outage window.
* Ablations (no forecast, no volume estimate, no fairness term) are retrained PPO policies; the trained actors are in `models/ablation/`.
* Outputs: `results/sim_episodes.csv` (one row per episode), `sim_summary.csv`, `sim_paired_stats.csv` (paired differences with 95 % intervals),
  `sim_tables.tex`, `meta.json` (software versions, parameters).
* Reading the results: the learned policy matches the rule-based heuristic and no ablated component has an effect larger than the
  per-episode spread; the centralised baseline's loss under packet loss follows from its assumed timeout.

### Software-in-the-loop deployment

**What this is.** The paper's red markers ask where the MQTT broker, the gateway and the dashboard ran in the laboratory and field trials. That
is not recorded, and nothing here recovers it. This is a *re-created reference deployment* on one Linux machine, used to measure what the
loss of each part does to service. It is not a measurement of the physical dispensers.

| Real | Simulated |
|---|---|
| `agent.main.Agent` with the real `MqttLink` or `LoraLink`, 10 agents | pump, tank, sensors and camera (`SimHardware`); the detector always says "valid, 500 ml" |
| Mosquitto 2.0.18 as an operating-system process, configuration in `deploy/mosquitto.sil.conf` | the SX1278 radio (`sim/sil/radio.py`, UDP on localhost, 5 % independent loss, no collisions or range) |
| `gateway/firebase_bridge.py` and `gateway/lora_gateway.py` as separate processes | the Firebase database (`sim/sil/firebase_stub.py` records the PUT requests); `RPi.GPIO` |
| paho-mqtt reconnect behaviour | the users (Poisson arrivals, one person at the sensor at a time, 120 s patience, 5 s walk when redirected) and the clock |

Not covered: Node-RED and the Angular Admin-Web (not run), the NB-IoT modem (see gap 10), the SX1278 driver (tested separately), real radio
propagation, and any field condition. Agents 1-5 have a 15 L tank; agents 6-10 hold 700 ml, enough for one 500 ml request, so their later
users need a neighbour. Each run has 300 simulated seconds and an outage window of 90-180 s; about 100 users per run, 5 seeds per scenario.

```bash
sudo apt-get install mosquitto            # the broker is started and stopped by the scripts
python -m sim.run_sil --seeds 5 --k 5     # 8 scenarios x 5 seeds, k = simulated seconds per real second; about 20 minutes
python -m sim.run_sil --seeds 5 --realtime        # MQTT broker-window scenario at k = 1 (about 15 minutes)
python -m sim.sil.reconnect_test          # real-time reconnect measurement (about four minutes)
python -m pytest tests/test_sil_smoke.py  # 40-second smoke test of the harness
```

Outputs: `results/sil/summary.md|csv` (k = 5), `summary_realtime.md|csv` (k = 1), `reconnect.json`, `meta.json`, and per-run folders in
`results/sil/runs*/` with every user's outcome (`users.csv`), the agents' own logs and the broker configuration used.

Success rate of users, by when they arrived (before / during / after the 90-180 s outage window), mean over 5 runs:

| Link | What is switched off | Before | During | After | Dashboard feed during |
|---|---|---|---|---|---|
| LoRa | nothing | 100 % | 100 % | 100 % | running (about 49 PUT/min) |
| LoRa | broker, 90 s | 100 % | 100 % | 100 % | stops |
| LoRa | broker, whole run | 100 % | 100 % | 100 % | none; gateway and bridge exit at start |
| LoRa | gateway, 90 s | 100 % | 100 % | 100 % | stops |
| MQTT | nothing | 100 % | 100 % | 100 % | running (about 52 PUT/min) |
| MQTT | Firebase bridge, 90 s | 100 % | 100 % | 100 % | stops |
| MQTT | broker, 90 s (k = 1) | 100 % | 95.9 % | 100 % | stops |
| MQTT | broker, whole run | 65.2 % | 50.6 % | 48.8 % | none; bridge exits at start |

Reading it:

* With the **LoRa link the agents never touch the broker**: neighbours talk over the radio and the gateway is a one-way bridge to MQTT.
  Losing the broker, the gateway or the dashboard path costs service nothing, only the monitoring feed.
* With the **MQTT link the broker is on the coordination path**. A dispenser with water serves its users whatever happens (high-tank users:
  100 % in every scenario). A dispenser that must pass a user to a neighbour can do so only while its neighbour information is fresh
  (30 s without a state message and it is stale; states are sent every 15 s). With no broker at all, users of the low-tank dispensers
  succeed 29 % / 2 % / 0 % (before / during / after): only each dispenser's first request is served.
* In the 90 s broker outage at real-time speed, 92 % of low-tank users were served in the window and 6 of about 508 users gave up after 120 s.
  Users who arrived in the first 15 s of the outage were redirected normally (about 5 s); those who arrived later waited for the broker, and
  across all users who arrived in the window the mean time to service was 36 s (95th percentile 116 s). Agents received their first neighbour message 37-47 s after the broker came
  back. The reconnect test measured 4.5 s, 0.5 s and 36.5 s after outages of 10 s, 30 s and 90 s (one run each; paho-mqtt's default back-off
  doubles from 1 s up to 120 s, so the delay depends on when the next attempt falls). The same scenario at k = 5 gives 88.3 % in the
  window, because that back-off runs in real seconds; quote the k = 1 run.
* A redirected user is told to walk to the neighbour when the forward is *sent*, before the acknowledgement. If the message is lost, the
  origin returns the request to its own queue (log: "request returned to local queue") while the user is already at the neighbour, which treats
  the arrival as a new request. Service continues, but the origin keeps a request nobody is waiting for until it times out.

## Quick start

```bash
pip install -r requirements/train.txt            # workstation
python -m pytest                                 # 56 tests collected
python -m train.train_ppo --timesteps 300000     # -> models/policy.npz (PyTorch process)
python -m train.train_forecaster --csv usage.csv # -> models/forecaster.tflite (TensorFlow process); --synthetic = smoke test only
python -m sim.run_experiment --seeds 30          # simulation table

# one simulated dispenser (no GPIO/camera; needs an MQTT broker on localhost)
python -m agent.main --simulate

# real dispenser (Raspberry Pi 4 / Jetson Nano)
pip install -r requirements/edge.txt
cp config/agent.example.yaml config/agent.yaml   # edit pins, link, agent_id, neighbours
python -m tools.calibrate_volume --config config/agent.yaml
python -m agent.main --config config/agent.yaml
```

`models/policy.npz` is a demo policy trained **in the simulator**; retrain after changing `sim/env.py` or `agent/spec.py`
(the observation layout must match between training and deployment).

## How to cite

`CITATION.cff` (GitHub's "Cite this repository" button) and `.zenodo.json` hold the citation metadata. Cite the paper for the
system and this repository for the code and simulation results:

> W. Chumyen, "Multi-Agent Smart Water Distribution with Computer Vision-Based Container Detection and AI-Driven Behavior
> Forecasting for Disaster Relief in Smart Cities," 2025 IEEE International Conference on Agentic AI (ICA), Wuhan, China,
> 2025, pp. 7-11, doi: 10.1109/ICA67499.2025.00011.

A versioned archive of this repository is deposited on Zenodo for each release; the DOI will be added here and to `CITATION.cff`
once the first release has been archived.

## Security notes

* `IOT/*.ino` no longer contain Wi-Fi credentials: copy `secrets.h.example` to `secrets.h` (git-ignored) in each sketch folder.
  Earlier commits still contain the old SSID/password in the public history - **change that Wi-Fi password**.
* `Admin-Web/.../environment.ts` contains a Firebase web API key. These keys are not secrets by themselves, but make sure the
  Realtime Database security rules do not allow public read/write.

## Suggested wording for the paper's Appendix A

"Code for the edge agent, simulator, training scripts and gateway is available at <repo>. The trained container-detection model and
real usage logs are not included; the repository provides the dataset export, training/export scripts and a simulator-trained demonstration policy."
