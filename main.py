import subprocess, json, sys, os, shutil, time, tempfile
import urllib.request, urllib.parse, ctypes
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if os.name == "nt":
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.system("cls")
else:
    os.system("clear")

RED, GREEN, YELLOW, CYAN, MAGENTA, WHITE, BOLD, RESET = (
    "\033[91m", "\033[92m", "\033[93m", "\033[96m",
    "\033[95m", "\033[97m", "\033[1m", "\033[0m"
)

BANNER = MAGENTA + BOLD + r"""
   ██████╗ ██╗████████╗██╗  ██╗██╗   ██╗██████╗     ███████╗██╗███╗   ██╗██████╗ ███████╗██████╗
  ██╔════╝ ██║╚══██╔══╝██║  ██║██║   ██║██╔══██╗    ██╔════╝██║████╗  ██║██╔══██╗██╔════╝██╔══██╗
  ██║  ███╗██║   ██║   ███████║██║   ██║██████╔╝    █████╗  ██║██╔██╗ ██║██║  ██║█████╗  ██████╔╝
  ██║   ██║██║   ██║   ██╔══██║██║   ██║██╔══██╗    ██╔══╝  ██║██║╚██╗██║██║  ██║██╔══╝  ██╔══██╗
  ╚██████╔╝██║   ██║   ██║  ██║╚██████╔╝██████╔╝    ██║     ██║██║ ╚████║██████╔╝███████╗██║  ██║
   ╚═════╝ ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═════╝     ╚═╝     ╚═╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝
""" + RESET

KNOWN_PATHS = [
    r"C:\Program Files\GitHub CLI\gh.exe",
    r"C:\Program Files (x86)\GitHub CLI\gh.exe",
    os.path.expanduser(r"~\AppData\Local\GitHubCLI\gh.exe"),
    os.path.expanduser(r"~\AppData\Local\Programs\GitHub CLI\gh.exe"),
    os.path.expanduser(r"~\scoop\apps\gh\current\bin\gh.exe"),
    r"C:\ProgramData\chocolatey\bin\gh.exe",
]

DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "github_finder")


def log(msg, color=RESET):
    try:
        print(color + msg + RESET, flush=True)
    except UnicodeEncodeError:
        print(msg, flush=True)


def input_line(prompt):
    try:
        return input(CYAN + BOLD + prompt + RESET).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def run_cmd(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "not found"
    except Exception as e:
        return 1, "", str(e)


def refresh_path():
    try:
        import winreg
        paths = []
        for root, sub in [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ]:
            try:
                with winreg.OpenKey(root, sub) as k:
                    v, _ = winreg.QueryValueEx(k, "Path")
                    paths.append(v)
            except OSError:
                pass
        if paths:
            os.environ["PATH"] = ";".join(paths) + ";" + os.environ.get("PATH", "")
    except Exception:
        pass


def find_gh():
    gh = shutil.which("gh")
    if gh and os.path.isfile(gh):
        return gh
    for p in KNOWN_PATHS:
        if os.path.isfile(p):
            return p
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        if os.path.isdir(base):
            try:
                for entry in os.listdir(base):
                    if "github" in entry.lower() or "gh cli" in entry.lower():
                        for sub in ["gh.exe", os.path.join("bin", "gh.exe")]:
                            t = os.path.join(base, entry, sub)
                            if os.path.isfile(t):
                                return t
            except OSError:
                pass
    return None


def wait_gh_file(timeout=180):
    start = time.time()
    while time.time() - start < timeout:
        for p in KNOWN_PATHS:
            if os.path.isfile(p):
                return p
        time.sleep(3)
    return None


def install_msi(msi_path):
    log("Requesting admin rights to install MSI...", YELLOW)
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "msiexec.exe",
            '/i "' + msi_path + '" /qb /norestart', None, 1)
        if ret <= 32:
            return False
        return True
    except Exception:
        return False


def install_gh():
    log("gh CLI not found. Installing...", YELLOW)
    code, _, _ = run_cmd(["winget", "--version"])
    if code == 0:
        try:
            subprocess.run([
                "winget", "install", "--id", "GitHub.cli", "-e",
                "--source", "winget",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ], encoding="utf-8", errors="replace")
        except Exception:
            pass
        refresh_path()
        gh = find_gh()
        if gh:
            return gh

    try:
        api_url = "https://api.github.com/repos/cli/cli/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "github-finder"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        msi_url = None
        for a in data.get("assets", []):
            if a.get("name", "").endswith("_windows_amd64.msi"):
                msi_url = a.get("browser_download_url")
                break
        if not msi_url:
            return None
        tmp = os.path.join(tempfile.gettempdir(), "gh_cli_setup.msi")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        urllib.request.urlretrieve(msi_url, tmp)
        if not install_msi(tmp):
            return None
        return wait_gh_file()
    except Exception:
        return None


def gh_status(gh):
    code, out, err = run_cmd([gh, "auth", "status"])
    return code == 0, out + "\n" + err


def ensure_login(gh):
    ok, _ = gh_status(gh)
    if ok:
        return True

    log("Not logged in. Browser login required.", YELLOW)
    try:
        subprocess.run([
            gh, "auth", "login", "--web", "--git-protocol", "https",
            "-s", "repo", "-s", "read:org", "-s", "gist", "-s", "workflow",
        ], encoding="utf-8", errors="replace")
    except KeyboardInterrupt:
        return False

    ok, _ = gh_status(gh)
    return ok


def gh_run(gh, cmd, silent=False):
    try:
        r = subprocess.run([gh] + cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        if not silent:
            log("Command error: " + str(e), RED)
        return ""
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        if err and not silent:
            if "rate limit" in err.lower():
                log("GitHub rate limit reached. Please wait a minute.", RED)
            else:
                log("Error: " + err, RED)
        return ""
    return (r.stdout or "").strip()


def gh_api(gh, path, silent=False, headers=None):
    cmd = ["api"]
    for h in (headers or []):
        cmd += ["-H", h]
    cmd.append(path)
    return gh_run(gh, cmd, silent=silent)


def search_repos(gh, query, limit=25):
    url = ("search/repositories?q=" + urllib.parse.quote(query)
           + "&per_page=" + str(limit))
    out = gh_api(gh, url)
    if not out:
        return []
    try:
        return json.loads(out).get("items", [])
    except Exception:
        return []


def get_default_branch(gh, repo_full):
    out = gh_api(gh, "repos/" + repo_full, silent=True)
    if not out:
        return "main"
    try:
        return json.loads(out).get("default_branch", "main")
    except Exception:
        return "main"


def download_zip(gh, repo_full, branch=None):
    if not branch:
        branch = get_default_branch(gh, repo_full)

    log("Downloading ZIP: {} @ {} ...".format(repo_full, branch), YELLOW)

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    zip_url = "https://codeload.github.com/{}/zip/refs/heads/{}".format(
        repo_full, branch
    )

    safe_name = repo_full.replace("/", "_") + "_" + branch + ".zip"
    dest = os.path.join(DOWNLOAD_DIR, safe_name)

    try:
        req = urllib.request.Request(
            zip_url, headers={"User-Agent": "github-finder"}
        )
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            total = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
                sys.stdout.write(
                    "\r" + CYAN + "Downloading: {:.2f} MB".format(
                        total / (1024 * 1024)
                    ) + "     " + RESET
                )
                sys.stdout.flush()
        print()
        log("Saved: " + dest, GREEN)
        log("Size: {:.2f} MB".format(os.path.getsize(dest) / (1024 * 1024)), GREEN)
        return dest
    except Exception as e:
        log("Download error: " + str(e), RED)
        return None


def is_valid_repo_format(text):
    parts = text.split("/")
    if len(parts) != 2:
        return False
    owner, name = parts
    if not owner or not name:
        return False
    if " " in owner or " " in name:
        return False
    return True


def main():
    print(BANNER, flush=True)

    refresh_path()
    gh = find_gh()
    if not gh:
        gh = install_gh()
        if not gh:
            log("Auto-install failed.", RED)
            input_line("Press Enter to exit...")
            sys.exit(1)

    if not ensure_login(gh):
        log("Cannot continue.", RED)
        input_line("Press Enter to exit...")
        sys.exit(1)

    log("Save folder: " + DOWNLOAD_DIR, CYAN)
    print()

    raw = input_line("Repo URL, owner/name, or search keyword: ")
    if not raw:
        sys.exit(0)

    cleaned = raw.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if cleaned.startswith("http"):
        cleaned = urllib.parse.urlparse(cleaned).path.strip("/")
    if cleaned.startswith("github.com/"):
        cleaned = cleaned[len("github.com/"):]

    if is_valid_repo_format(cleaned):
        info = gh_api(gh, "repos/" + cleaned, silent=True)
        if info:
            download_zip(gh, cleaned)
            input_line("Press Enter to exit...")
            return
        log("Repo '{}' not found. Searching instead...".format(cleaned), YELLOW)

    log("Searching repositories for: " + raw, YELLOW)
    items = search_repos(gh, raw, 25)
    if not items:
        log("No repositories found.", RED)
        input_line("Press Enter to exit...")
        return

    print()
    log("Found {} repo(s).".format(len(items)), GREEN)
    print()
    for i, it in enumerate(items, 1):
        full = it.get("full_name", "?")
        lang = it.get("language") or "-"
        stars = it.get("stargazers_count", 0)
        print("  " + GREEN + BOLD + "[{:>2}]".format(i) + RESET
              + "  " + CYAN + full + RESET
              + "  " + MAGENTA + "★" + str(stars) + RESET
              + "  " + YELLOW + lang + RESET)
    print()

    choice = input_line("Select number to download ZIP: ")
    if not choice:
        return

    try:
        n = int(choice)
    except ValueError:
        log("Invalid number.", RED)
        input_line("Press Enter to exit...")
        return

    if n < 1 or n > len(items):
        log("Out of range.", RED)
        input_line("Press Enter to exit...")
        return

    full = items[n - 1].get("full_name")
    if not full:
        log("Missing repo name.", RED)
        input_line("Press Enter to exit...")
        return

    download_zip(gh, full)
    input_line("Press Enter to exit...")


if __name__ == "__main__":
    main()