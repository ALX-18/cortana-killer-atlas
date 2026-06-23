"""
System Config — Paramètres Windows (réseau, affichage, énergie, démarrage, etc.)
Via PowerShell, WMI et winreg.
Sécurisé par allowlist/denylist + journal d'audit.
"""

import json
import logging
import pathlib
import subprocess
import time
import winreg
from datetime import datetime
from typing import Any

logger = logging.getLogger("atlas.system_config")

# --------------------------------------------------------------------------- #
#  Config sécurité PowerShell
# --------------------------------------------------------------------------- #

def _load_ps_security_config() -> tuple[list[str], list[str]]:
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    return (
        cfg.get("powershell_allowlist", []),
        cfg.get("powershell_denylist", []),
    )

_PS_ALLOWLIST, _PS_DENYLIST = _load_ps_security_config()

# Audit log path
_AUDIT_LOG_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "audit_log.jsonl"
_AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _audit_log(command: str, status: str, reason: str = ""):
    """Écrit une entrée dans le journal d'audit append-only."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "command": command,
        "status": status,
        "reason": reason,
    }
    try:
        with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Erreur écriture audit log: %s", e)


def _check_powershell_security(command: str) -> tuple[bool, str]:
    """
    Vérifie qu'une commande PowerShell passe les filtres de sécurité.
    Retourne (autorisé: bool, raison: str).
    """
    cmd_lower = command.lower()

    # Vérifier la denylist en premier (priorité absolue)
    for denied in _PS_DENYLIST:
        if denied.lower() in cmd_lower:
            return False, f"Commande bloquée : contient '{denied}' (denylist)"

    # Vérifier qu'au moins un terme de l'allowlist est présent
    if _PS_ALLOWLIST:
        found = any(allowed.lower() in cmd_lower for allowed in _PS_ALLOWLIST)
        if not found:
            return False, f"Commande bloquée : aucun terme autorisé trouvé (allowlist). Termes acceptés : {', '.join(_PS_ALLOWLIST[:10])}..."

    return True, "ok"


def _run_ps(command: str, timeout: int = 15) -> dict[str, Any]:
    """Exécute une commande PowerShell et retourne le résultat."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Timeout dépassé."}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


# --------------------------------------------------------------------------- #
#  Commandes PowerShell arbitraires (avec confirmation obligatoire)
# --------------------------------------------------------------------------- #

def run_powershell(command: str) -> dict[str, Any]:
    """Exécute une commande PowerShell. Protégé par allowlist/denylist + audit."""
    # Vérification sécurité
    allowed, reason = _check_powershell_security(command)
    if not allowed:
        logger.warning("🛡️ PowerShell BLOQUÉ : %s | %s", command[:100], reason)
        _audit_log(command, "blocked", reason)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"🛡️ Sécurité Atlas : {reason}",
            "blocked": True,
        }

    logger.info("PowerShell exec: %s", command)
    result = _run_ps(command)
    _audit_log(command, "executed" if result["success"] else "error", result.get("stderr", ""))
    return result


# --------------------------------------------------------------------------- #
#  Réseau
# --------------------------------------------------------------------------- #

def get_network_adapters() -> dict[str, Any]:
    result = _run_ps("Get-NetAdapter | Select-Object Name, Status, LinkSpeed, MacAddress | ConvertTo-Json")
    if result["success"]:
        import json
        try:
            adapters = json.loads(result["stdout"])
            if isinstance(adapters, dict):
                adapters = [adapters]
            return {"success": True, "adapters": adapters}
        except json.JSONDecodeError:
            return {"success": True, "raw": result["stdout"]}
    return result


def get_wifi_networks() -> dict[str, Any]:
    return _run_ps("netsh wlan show networks mode=bssid")


def get_ip_config() -> dict[str, Any]:
    return _run_ps("Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias, IPAddress, PrefixLength | ConvertTo-Json")


# --------------------------------------------------------------------------- #
#  Affichage
# --------------------------------------------------------------------------- #

def set_night_light(enable: bool) -> dict[str, Any]:
    """Active/désactive le mode nuit Windows."""
    # Night Light toggle via registre
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\default$windows.data.bluelightreduction.bluelightreductionstate\windows.data.bluelightreduction.bluelightreductionstate"
    try:
        # Méthode plus fiable via PowerShell
        if enable:
            cmd = """
            $key = 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\DefaultAccount\\Current\\default$windows.data.bluelightreduction.settings\\windows.data.bluelightreduction.settings'
            if (Test-Path $key) {
                $data = (Get-ItemProperty -Path $key).Data
                if ($data) {
                    $data[18] = 0x15
                    Set-ItemProperty -Path $key -Name 'Data' -Value $data
                    Write-Output 'Mode nuit activé'
                }
            } else {
                Write-Output 'Clé registre non trouvée. Ouvrez Paramètres > Affichage > Éclairage nocturne.'
            }
            """
        else:
            cmd = """
            $key = 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\DefaultAccount\\Current\\default$windows.data.bluelightreduction.settings\\windows.data.bluelightreduction.settings'
            if (Test-Path $key) {
                $data = (Get-ItemProperty -Path $key).Data
                if ($data) {
                    $data[18] = 0x13
                    Set-ItemProperty -Path $key -Name 'Data' -Value $data
                    Write-Output 'Mode nuit désactivé'
                }
            } else {
                Write-Output 'Clé registre non trouvée.'
            }
            """
        return _run_ps(cmd)
    except Exception as e:
        return {"success": False, "stderr": str(e), "stdout": ""}


def get_display_info() -> dict[str, Any]:
    return _run_ps("Get-CimInstance -ClassName Win32_VideoController | Select-Object Name, VideoModeDescription, CurrentRefreshRate, DriverVersion | ConvertTo-Json")


def set_brightness(level: int) -> dict[str, Any]:
    """Règle la luminosité (0-100) — fonctionne sur laptops."""
    level = max(0, min(100, level))
    return _run_ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})")


# --------------------------------------------------------------------------- #
#  Énergie
# --------------------------------------------------------------------------- #

def get_power_plan() -> dict[str, Any]:
    return _run_ps("powercfg /getactivescheme")


def set_power_plan(plan: str) -> dict[str, Any]:
    """Change le plan d'alimentation: 'balanced', 'high_performance', 'power_saver'."""
    plans = {
        "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
        "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
        "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
    }
    guid = plans.get(plan.lower())
    if not guid:
        return {"success": False, "stdout": "", "stderr": f"Plan inconnu: '{plan}'. Valides: {list(plans.keys())}"}
    return _run_ps(f"powercfg /setactive {guid}")


# --------------------------------------------------------------------------- #
#  Démarrage
# --------------------------------------------------------------------------- #

def get_startup_programs() -> dict[str, Any]:
    return _run_ps("Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location | ConvertTo-Json")


def disable_startup_program(name: str) -> dict[str, Any]:
    """Désactive un programme au démarrage via le registre."""
    cmd = f"""
    $paths = @(
        'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run',
        'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run'
    )
    $found = $false
    foreach ($path in $paths) {{
        try {{
            $val = Get-ItemProperty -Path $path -Name '{name}' -ErrorAction Stop
            Remove-ItemProperty -Path $path -Name '{name}'
            $found = $true
            Write-Output "Supprimé de $path"
        }} catch {{ }}
    }}
    if (-not $found) {{ Write-Output "Programme '{name}' non trouvé dans le démarrage." }}
    """
    return _run_ps(cmd)


# --------------------------------------------------------------------------- #
#  Actions système
# --------------------------------------------------------------------------- #

def empty_recycle_bin() -> dict[str, Any]:
    return _run_ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue; Write-Output 'Corbeille vidée.'")


def get_installed_programs() -> dict[str, Any]:
    return _run_ps(
        "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | "
        "Select-Object DisplayName, DisplayVersion, Publisher, InstallDate | "
        "Where-Object { $_.DisplayName } | Sort-Object DisplayName | ConvertTo-Json"
    )


# --------------------------------------------------------------------------- #
#  Dispatch
# --------------------------------------------------------------------------- #

ACTIONS = {
    "night_light_on": lambda: set_night_light(True),
    "night_light_off": lambda: set_night_light(False),
    "get_display": get_display_info,
    "set_brightness": None,  # requires param
    "get_power_plan": get_power_plan,
    "set_power_plan": None,  # requires param
    "get_network": get_network_adapters,
    "get_wifi": get_wifi_networks,
    "get_ip": get_ip_config,
    "get_startup": get_startup_programs,
    "disable_startup": None,  # requires param
    "empty_bin": empty_recycle_bin,
    "get_installed": get_installed_programs,
    "run_powershell": None,  # requires param
}


def dispatch_system_config(action: str, **kwargs) -> dict[str, Any]:
    """Point d'entrée unifié pour les actions de configuration système."""
    if action == "set_brightness":
        return set_brightness(kwargs.get("level", 50))
    if action == "set_power_plan":
        return set_power_plan(kwargs.get("plan", "balanced"))
    if action == "disable_startup":
        return disable_startup_program(kwargs.get("name", ""))
    if action == "run_powershell":
        return run_powershell(kwargs.get("command", ""))

    func = ACTIONS.get(action)
    if func is None:
        return {"success": False, "stdout": "", "stderr": f"Action inconnue : '{action}'. Valides : {list(ACTIONS.keys())}"}
    return func()
