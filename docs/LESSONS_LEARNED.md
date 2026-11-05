# Lessons learned (GenVM)

- Studio rejects long comments and docstrings with `invalid_contract`; the deploy file is generated with `ast`, never regex.
- TreeMap and DynArray are zero-initialized; assigning `{}` or `[]` in `__init__` crashes.
- TreeMap is dict-like (`m[k] = v`, `k in m`, `m.get(k)`); it has no `.set()` or `.contains()`.
- Storage cannot be used inside nondet blocks; pass plain values into module-level functions.
- Exceptions inside the leader closure must be caught inside it and returned as a marker.
- Compare verdicts exactly across validators; never compare byte-exact hashes of web content.
- Payable calls that revert keep the value; refund invalid input into a pull balance instead.
- Ground every positive verdict in fetched evidence and an exact quoted substring.
- Registration after the evidence snapshot must not make a juror eligible; re-entry resets the timestamp.
