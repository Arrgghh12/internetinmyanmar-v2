# Social Campaign — OONI Probe Article

Article: https://www.internetinmyanmar.com/articles/ooni-probe-myanmar-censorship-data/
OG image: https://www.internetinmyanmar.com/og-default.png

Platforms: X and Facebook only (no LinkedIn). Posted simultaneously per wave.
Schedule: Day 1, Day 3, Day 7.

---

## Wave 1 — Day 1 ✓ POSTED 2026-04-30

### X
```
In Myanmar: Signal (90.3%), WhatsApp (89.9%), Messenger (90.9%), Tor (88.1%) — all blocked. Feb 2026 routing shift signals a national firewall now operational. Source: OONI probe data. #Myanmar #OONI
https://www.internetinmyanmar.com/articles/ooni-probe-myanmar-censorship-data/
```
Tweet ID: 2050200137494896789

### Facebook
```
Myanmar's internet blocks Signal at 90.3%, WhatsApp at 89.9%, and Facebook Messenger at 90.9% — verified by OONI probe data. Tor is also blocked at 88.1%. These are not estimates; they are measured anomaly rates from active network measurements inside the country.

The February 2026 routing shift marks a structural change: a national firewall entering operation. Without volunteers running probes, these blocks would remain invisible. Data collection is the only way to document censorship in real time.

#Myanmar #InternetFreedom
https://www.internetinmyanmar.com/articles/ooni-probe-myanmar-censorship-data/
```
Post ID: 1183169741738159_1581294224002442

---

## Wave 2 — Day 3 (post ~2026-05-03)

### X (≤280 chars total with URL)
Text to pass to post_twitter() [URL appended automatically]:
```
Myanmar's 13.4% internet anomaly rate covers only networks where probes can reach. 131+ townships under communications blackout produce zero OONI measurements — the real censorship picture is worse. #Myanmar #InternetFreedom
```

### Facebook
Text to pass to post_facebook() [URL appended automatically]:
```
Myanmar's official anomaly rate is 13.4% — but that number only covers places where probes can reach. More than 131 townships have been under complete communications blackout since 2021, producing zero OONI measurements.

The data we have understates the reality. The populations most affected — in Shan, Kayah, Kachin, and Rakhine States — are precisely the ones that don't appear in the dataset.

Understanding the coverage gap is essential to interpreting Myanmar's internet freedom data correctly.

#Myanmar #InternetFreedom
```

---

## Wave 3 — Day 7 (post ~2026-05-07)

### X (≤280 chars total with URL)
Text to pass to post_twitter() [URL appended automatically]:
```
Myanmar's 13.4% anomaly rate exists because volunteers run OONI probes. Signal, WhatsApp, Messenger, Tor — all blocked 88–91%. The Feb 2026 routing shift suggests a national firewall is now operational. Install OONI Probe. #Myanmar #OONI
```

### Facebook
Text to pass to post_facebook() [URL appended automatically]:
```
Two weeks ago, we published data showing Myanmar's internet has entered a new phase: a national firewall consistent with Chinese Great Firewall-style infrastructure, operating since February 2026.

Signal (90.3%), WhatsApp (89.9%), Facebook Messenger (90.9%), and Tor (88.1%) are all blocked at the network layer — not by app restrictions, but by deep packet inspection that ISPs must operate under the 2025 Cybersecurity Law.

This record exists because volunteers run OONI probes. The more probes run on diverse networks, the harder censorship is to hide. Open datasets: https://www.internetinmyanmar.com/observatory/data/

#Myanmar #OONI #InternetFreedom
```

---

## Execution scripts

Wave 2 script: /tmp/post_wave2.py (create when ready to post)
Wave 3 script: /tmp/post_wave3.py (create when ready to post)

Pattern:
```python
from social_poster import post_twitter, post_facebook, download_image
image_path = download_image("https://www.internetinmyanmar.com/og-default.png")
post_twitter(TWITTER_TEXT, ARTICLE_URL, image_path=image_path)
post_facebook(FACEBOOK_TEXT, ARTICLE_URL, image_url="https://www.internetinmyanmar.com/og-default.png")
```
