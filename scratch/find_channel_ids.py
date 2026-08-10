import urllib.request
import re

url = 'https://www.youtube.com/@Ironmouse'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8')
        cids = re.findall(r'UC[a-zA-Z0-9_-]{22}', html)
        print("All candidate CIDs:", set(cids))
except Exception as e:
    print("Error:", e)
