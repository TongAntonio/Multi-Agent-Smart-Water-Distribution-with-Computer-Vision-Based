"""Agent configuration: defaults + YAML override. Pin numbers are BCM (Raspberry Pi 4 / Jetson Nano 40-pin header)."""
from __future__ import annotations

import copy

DEFAULTS = {
    "agent_id": 1,
    "neighbors": [],                 # ids of neighbouring dispensers (LoRa range / same MQTT topic space)
    "simulate_hardware": False,
    "tick_s": 0.25,
    "request_timeout_s": 120.0,
    "state_period_s": 15.0,
    "forward_ack_timeout_s": 3.0,
    "forward_retries": 2,
    "default_volume_ml": 500,        # used only when the CV volume estimate is unavailable
    "reserve_ml": 200,               # never dispense the tank below this level
    "hardware": {
        "pins": {"us_trig": 23, "us_echo": 24, "ir": 17, "pump_relay": 27, "dht": "D4"},
        "ir_active_low": True,       # E18-D80NK pulls the line LOW on detection
        "pump_active_low": True,
        "flow_ml_per_s": 50.0,       # MUST be calibrated on your pump
        "max_dispense_s": 20.0,
        "tank": {"empty_distance_cm": 40.0, "full_distance_cm": 5.0, "capacity_ml": 20000},
    },
    "camera": {"backend": "auto", "index": 0, "width": 640, "height": 480},
    "cv": {
        "model": "models/container_ssd.tflite",
        "labels": "models/labels.txt",
        "valid_label": "The cup is able to supply water",
        "calibration": "models/volume_calibration.json",
        "score_threshold": 0.5,
        "class_offset": 0,
        "output_order": ["boxes", "classes", "scores", "count"],
        "allow_without_model": False,   # if True the agent dispenses on IR presence alone (NOT recommended)
    },
    "forecast": {"model": "models/forecaster.tflite", "stats": "models/forecaster_stats.json",
                 "bin_s": 60, "window": 12, "horizon_bins": 5},
    "policy": {"path": "models/policy.npz"},
    "link": {
        "type": "mqtt",              # mqtt | lora | nbiot | memory
        "mqtt": {"host": "localhost", "port": 1883, "prefix": "water", "username": None, "password": None},
        "lora": {"freq_hz": 433_175_000, "sf": 9, "bw_hz": 125_000, "cr": 5, "tx_power_dbm": 14,
                 "spi_bus": 0, "spi_cs": 0, "reset_pin": 25, "sync_word": 0x12},
        "nbiot": {"port": "/dev/serial0", "baud": 115200, "apn": "", "activate_cmd": 'AT+CNACT=0,1',
                  "host": "localhost", "mqtt_port": 1883, "prefix": "water"},
    },
    "log_dir": "logs",
}


def _merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: str | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        import yaml
        with open(path) as f:
            _merge(cfg, yaml.safe_load(f) or {})
    return cfg
