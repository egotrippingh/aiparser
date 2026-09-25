"""Store the service key in the ignored local server/.env without console echo."""

from pathlib import Path
import msvcrt


def main() -> None:
    print("OpenRouter key: ", end="", flush=True)
    chars = []
    while (char := msvcrt.getwch()) not in ("\r", "\n"):
        chars.append(char)
    print(flush=True)
    key = "".join(chars).strip()
    if not key.startswith("sk-or-v1-"):
        raise SystemExit("Invalid key format")
    path = Path(__file__).resolve().parents[1] / "server" / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    managed_names = ("OPENROUTER_API_KEY=", "OPENROUTER_PRIMARY_MODEL=", "OPENROUTER_ARBITER_MODEL=")
    lines = [line for line in lines if not line.startswith(managed_names)]
    lines.extend((f"OPENROUTER_API_KEY={key}",
                  "OPENROUTER_PRIMARY_MODEL=google/gemini-3.1-flash-lite",
                  "OPENROUTER_ARBITER_MODEL=google/gemini-3.8-flash"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Saved OpenRouter server configuration in ignored server/.env")


if __name__ == "__main__":
    main()
