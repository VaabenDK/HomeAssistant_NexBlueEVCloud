from homeassistant.const import Platform


DOMAIN = "nexblue"

PLATFORMS: list[Platform] = [
	Platform.SENSOR,
	Platform.SWITCH,
	Platform.NUMBER,
	Platform.SELECT,
]

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ACCOUNT_TYPE = "account_type"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60
DEFAULT_ACCOUNT_TYPE = 0

ACCOUNT_TYPE_END_USER = 0
ACCOUNT_TYPE_INSTALLER = 1

CHARGER_STATE_MAP = {
	0: "idle",
	1: "connected",
	2: "charging",
	3: "finished",
	4: "error",
	5: "lb_waiting",
	6: "delay_waiting",
	7: "ev_waiting",
}

SCHEDULE_MODE_MAP = {
	0: "off_peak",
	1: "eco",
	2: "schedule_charge",
}

SELECTABLE_SCHEDULE_MODES = {0, 2}

SCHEDULE_MODE_LABELS = {
	"off_peak": "Off-peak",
	"schedule_charge": "Scheduled",
	"eco": "Eco",
}

SCHEDULE_MODE_REVERSE_MAP = {value: key for key, value in SCHEDULE_MODE_MAP.items()}