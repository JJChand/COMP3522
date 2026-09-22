# Analysis organization

Use one numbered folder per research direction. Keep the code, a short method
note, and generated outputs together so each result can be reproduced without
searching across the repository.

```text
analyses/
  00_data_access/       # connection and source-data feasibility checks
  01_<direction>/       # future research direction
    README.md
    <scripts>
    results/
```

Generated files belong in the analysis folder's `results/` directory. Result
contents are ignored by Git by default because database extracts may be large;
promote only small, reviewed outputs into version control deliberately.
