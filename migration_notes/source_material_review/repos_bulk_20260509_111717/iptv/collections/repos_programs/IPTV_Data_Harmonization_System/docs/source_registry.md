# Source Registry

**Version:** 2025-09-21  
**Format:** YAML

## Sample Entries
```yaml
- name: epg_CA
  type: epg
  country: CA
  url: https://epg.pw/xmltv/epg_CA.xml.gz
  format: xmltv
  update: daily
  decompress: true

- name: epg_US
  type: epg
  country: US
  url: https://epg.pw/xmltv/epg_US.xml.gz
  format: xmltv
  update: daily
  decompress: true

- name: m3u_US
  type: m3u
  country: US
  url: https://freetv.fun/test_channels_united_states_new.m3u
  format: m3u
  update: weekly

- name: m3u_CA
  type: m3u
  country: CA
  url: https://freetv.fun/test_channels_canada_new.m3u
  format: m3u
  update: weekly

- name: m3u_UK
  type: m3u
  country: UK
  url: https://freetv.fun/test_channels_united_kingdom_new.m3u
  format: m3u
  update: weekly

- name: m3u_AU
  type: m3u
  country: AU
  url: https://freetv.fun/test_channels_australia_new.m3u
  format: m3u
  update: weekly

- name: m3u_movies
  type: m3u
  country: ALL
  url: https://freetv.fun/test_channels_movies_new.m3u
  format: m3u
  update: weekly
