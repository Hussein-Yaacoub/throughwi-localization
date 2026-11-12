# Residential recordings

The archive contains 29 study recordings from the team's localization capture export. These are gzip-compressed CSVs named as in the original metadata. Each has the header `ts_ms,rssi,chan,mac,csi_len,csi_raw`. Timestamps are board uptime in milliseconds, RSSI is in dBm, and `csi_raw` contains space-delimited signed bytes. The `mac` column contains four synthetic aliases preserving which packets belong to the same access point. The source mapping is excluded.

[recordings.csv](recordings.csv) contains the original nominal geometry and scenario labels. The coordinate origin in the horizontal plane is the ESP32, positive x points toward the router, positive y points right when facing the router, and z is the height above the floor. Blank coordinates or split mean the run is outside the stationary single-person localization subset. The manifest also records one 100-packet tail trim from the historical cleaner. The unlabeled `aside.csv` and the four separate hand-motion captures sit outside this study subset.

| Subset | Recordings | Packets after cleaning |
| --- | ---: | ---: |
| All mapped recordings | 29 | 43,147 |
| Localization train | 12 | 17,888 |
| Localization validation | 2 | 2,983 |
| Localization test | 4 | 5,941 |

The manifest records the split obtained by sorting and shuffling the 18 eligible filenames with NumPy RandomState seed 42, then allocating 12/2/4 files. One nominal position, `(2, 0, 1)` m, occurs in train and test under distinct geometries. All residential z labels are 1 m. The test recordings comprise three same-room placements and one placement in a two-wall setup. The partitioning keeps each continuous recording within a single subset and describes evaluation within the collected residential campaign.

The team has approved public release of the repository. The distributed recordings use synthetic access-point aliases. New captures should undergo the same identifier review before being added.
