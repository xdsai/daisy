# iOS Shortcut - Simple Version

This is the **easiest way** to search and download torrents from your iPhone.

## Setup (One Time)

1. Make sure API server is running on your server:
```bash
export DAISY_API_KEY="your-secret-key"
python3 api_server.py
```

2. Note your server IP (e.g., `192.168.0.101`) and API key

## Create the Shortcut

Open **Shortcuts** app and create a new shortcut with these actions:

### 1. Ask for Input
- **Prompt**: "What do you want to download?"
- **Type**: Text

### 2. Get Contents of URL (Search)
- **URL**: `http://YOUR_IP:5000/search`
- **Method**: GET
- **Headers**:
  - Add Header: `X-API-Key` = `your-secret-key`
- **Add to URL** (query parameters):
  - `q` = `Provided Input` (from step 1)
  - `limit` = `10`

### 3. Get Dictionary Value (Results)
- **Get**: `results`
- **From**: `Contents of URL`

### 4. Get Dictionary Value (Display Text)
- **Get**: `display_text`
- **From**: `Dictionary Value`

This creates a list of formatted text like:
```
#0 Perfect Blue (1997) [1080p]
👥 234 seeders | 💾 1.4 GiB | ⭐ 2390
```

### 5. Choose from List
- **Prompt**: "Select torrent"
- **List**: `Dictionary Value` (from step 4)
- **Select Multiple**: OFF

### 6. Get Item from List
- **Get**: `Item At Index`
- **Index**: Extract the number after `#` from `Chosen Item` using **Match Text**
  - **Text**: `Chosen Item`
  - **Pattern**: `#(\d+)`
  - **Group**: 1
- **From**: `Dictionary Value` (from step 3 - the FULL results list)

Wait, that's complex. Let me simplify...

### **SIMPLER APPROACH:**

After step 3 (Get results list), do this:

### 4. Repeat with Each (Loop through results)
- **Input**: `Dictionary Value` (the results list)

### 5. Get Dictionary Values (Inside repeat)
Get these values from `Repeat Item`:
- `index`
- `display_text`
- `magnet`

### 6. Create Dictionary (Inside repeat)
Create a dictionary with:
- `text` = `display_text`
- `magnet` = `magnet`
- `index` = `index`

This gives you a NEW list where each item has both the display text AND the magnet.

### 7. Choose from List (After repeat)
- **Prompt**: "Select torrent"
- **List**: Get `text` from `Repeat Results`

### 8. Find (Get the selected item)
- **Find**: Items where `text` = `Chosen Item`
- **In**: `Repeat Results` (the dictionaries we created)

### 9. Get Dictionary Value (Get Magnet)
- **Get**: `magnet`
- **From**: `Items` (from Find)

### 10. Get Dictionary Value (Get Index)
- **Get**: `index`
- **From**: `Items`

### 11. Get Contents of URL (Download)
- **URL**: `http://YOUR_IP:5000/download`
- **Method**: POST
- **Headers**:
  - `X-API-Key` = `your-secret-key`
  - `Content-Type` = `application/json`
- **Request Body**: JSON
```json
{
  "magnet": "Dictionary Value (magnet)",
  "name": "Provided Input",
  "type": "other"
}
```

### 12. Show Notification
- **Text**: "Download started!"

---

## Even EASIER: Use Index Directly

Actually, the API response now includes an `index` field in each result (0, 1, 2, etc.).

Here's the **simplest** shortcut:

### Actions:

1. **Ask for Input** - "What to download?"

2. **Get URL** - Search endpoint with your query

3. **Get Dictionary Value** - `results` from response

4. **Repeat with Each** - Loop through results
   - **Get Dictionary Value** - `display_text` from Repeat Item
   - **Add to List** - Add display_text to a new list

5. **Choose from List** - Show the list of display_text

6. **Match Text** - Extract `#0`, `#1`, etc. from chosen item
   - Pattern: `#(\d+)`

7. **Get Item from List** - Use matched number as index to get result from step 3

8. **Get Dictionary Value** - `magnet` from selected result

9. **Post to Download** endpoint with the magnet

10. **Show Notification**

---

## Test It

Search for "perfect blue" - you should see:
```
#0 Perfect Blue (1997) [1080p] BluRay
👥 156 seeders | 💾 1.4 GiB | ⭐ 1610

#1 Perfect Blue 1997 1080p
👥 89 seeders | 💾 1.3 GiB | ⭐ 920
```

Pick one, it downloads!

---

## The Key Insight

Each search result now has:
- `index`: 0, 1, 2, 3...
- `display_text`: Pretty formatted text with the index
- `magnet`: The actual magnet link

So you can:
1. Show `display_text` in the list
2. Parse the index from chosen text (`#0` → `0`)
3. Use that index to grab the original result with the magnet

The `display_text` acts as a "label" but the full data is preserved!
