# Dr Aura — Full Group Management Bot v1.1

**Owner:** King Khalid (`8333953794`)  
**Token:** set in `config.py`

## Features

### 01 Moderation
`/ban` `/tban` `/unban` `/kick` `/mute` `/tmute` `/unmute`

### 02 Warnings
`/warn` `/unwarn` `/warns` `/resetwarns` — auto-ban when limit reached

### 03 Locks
`/lock` `/unlock` `/locks`  
Types: `all` `media` `url` `gif` `photo` `video` `audio` `document` `sticker` `emoji` `forward` `bot` `command` `text`

### 04 Anti systems
- `/antilink off|del|kick|ban|mute`
- `/antidelete on|off` — caches messages (text/photo/sticker/file/video/audio)

### 05 Welcome / Rules
`/setwelcome` `/setgoodbye` `/setrules` `/rules`  
Placeholders: `{name}` `{mention}` `{id}` `{group}`

### 06 Notes
`/save name` `/get name` `/notes` `/clear name`  
Trigger in chat with `#name` (supports media)

### 07 Filters
`/filter keyword reply` `/stop keyword` `/filters`  
Auto-replies when keyword appears (media supported)

### 08 Force Join
`/forcejoin add @channel` `/forcejoin del @channel` `/forcejoin clear`  
Blocks messages until user joins required channels/groups

### 09 Federation
`/newfed Name` `/joinfed FED_ID` `/leavefed FED_ID`  
`/fedban` `/fedunban` `/fedinfo` — shared bans across all fed groups

### 10 Info
`/id` `/adminlist` `/help` `/version` `/ping`

### 11 Owner / Developer
`/owner` `/stats` `/broadcast` `/gbroadcast`  
`/addsudo` `/delsudo` `/sudolist`  
`/emojitoggle` `/setemo KEY EMOJI_ID FALLBACK`  
`/backup` `/maintenance` `/health` `/uptime`  
`/banuser` `/unbanuser` (global bot ban)

### Premium Emoji
- ON by default with your emoji IDs
- `/emojitoggle` — turn off/on
- `/setemo fire 5289722755871162900 🔥` — custom mapping

## Run

```bash
cd dr_aura_bot
pip install -r requirements.txt
python bot.py
```

Promote bot as **admin** with Delete Messages + Restrict Members in every group.

## Roadmap still open
Captcha / anti-raid UI, import-export settings, timed locks, plugin loader, full audit logs UI
