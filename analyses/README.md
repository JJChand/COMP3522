# Analysis organization

Use one numbered folder per research direction. Keep the code, a short method
note, and generated outputs together so each result can be reproduced without
searching across the repository.

```text
analyses/
  00_data_access/       # connection and source-data feasibility checks
  01_rainfall/          # macOS rainfall access and coverage checks
  02_<direction>/       # future research direction
    README.md
    <scripts>
    results/
```

Generated files belong in the analysis folder's `results/` directory. Result
contents are ignored by Git by default because database extracts may be large;
promote only small, reviewed outputs into version control deliberately. The
rainfall procedure reads the existing database without saving raw observations.
Its requested research CSVs and plots are aggregate outputs in
`01_rainfall/results/`.
