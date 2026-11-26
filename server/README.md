# Running Twisty from your home PC

Your PC does the heavy work (scoring every road in Scotland, and turn-by-turn routing). Your phone reaches it
privately through Tailscale, so nobody else can open it.

## 1. Get the code (once)

```bash
git clone https://github.com/ROLEGUIDE/SpiritedSearch.git
cd SpiritedSearch/server
chmod +x setup.sh start.sh
```

## 2. Set up (once, 10–20 minutes)

```bash
sudo dnf install -y podman python3   # usually already installed on Nobara
./setup.sh
```

This downloads Scotland's map data, scores every road and prepares routing. To refresh the map data later:
`REFRESH=1 ./setup.sh`

## 3. Start it (each time you want to use it)

```bash
./start.sh
```

Leave that terminal open. On the PC you can check it at http://127.0.0.1:8080

## 4. Reach it from your phone with Tailscale (once)

1. On the PC: `curl -fsSL https://tailscale.com/install.sh | sh` then `sudo tailscale up` and sign in.
2. On your phone: install **Tailscale** from the Play Store and sign in with the same account.
3. On the PC: `sudo tailscale serve --bg 8080`
   The first time, it gives you a link to switch on HTTPS for your account. Open it, switch it on, then run the command again.
4. It prints your app's address, something like `https://your-pc-name.tail1234.ts.net`. Open that on your phone in Chrome.

Only devices signed in to your Tailscale account can open that address. The PC needs to be on and `./start.sh` running.

## Updating the app

```bash
cd SpiritedSearch && git pull
```
Then restart `./start.sh`.
