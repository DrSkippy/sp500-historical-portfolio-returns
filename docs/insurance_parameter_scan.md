# Insurance parameter scan: can crash insurance beat Fractional Kelly?

*Run 2026-10-07 on `main` at `e69319c` (`MODEL_VERSION = 2`). Scripts and raw results are in
[`notebooks/insurance_scan/`](../notebooks/insurance_scan/).*

## Question

Which insurance parameters — **cost** (`premium_rate`), **market drop** (`insurance_deductible`)
and **payout** (`coverage_ratio`) — let the Insurance strategy beat the best Fractional Kelly
variant in the grid, and are those parameters realistic?

## Short answer

- Insurance beats the best Kelly variant on return only when the premium is at or below what
  the policy actually paid out historically (its **fair premium**). For 5–9% deductibles the
  break-even premium is **0.8–1.1× fair**; no seller prices crash protection at or below fair.
- Beating Kelly on return is a low bar on the S&P 500: **Buy & Hold already beats every Kelly
  variant** by 0.07–0.39 points a year. A 12% deductible "beats Kelly" up to 3–4× fair purely
  because the portfolio is ~95% stocks; against Buy & Hold its break-even is ~1× fair.
- Beating Kelly on **risk** (share of losing start dates) as well needs **double coverage
  priced at 0.1–0.5× fair** — a leveraged crash bet bought at a fraction of its cost.
- **No practically priced setting adds value over Buy & Hold.** The published grid in
  `config.yaml` is unchanged.

## The model being tuned

The policy insures the stock, not the cash (see [README](../README.md#insurance-insurancemodel)):

```
premium (per day) = premium_rate × insured stock value / 365          # charged from cash
trigger           = 6-day price loss ≥ insurance_deductible
payout            = coverage_ratio × insured_value × (|loss| − deductible)   # into cash
```

At most one payout per 90-day policy period; same-day rebalance after a payout. All scans use
a 5% cash reserve (`insurance_frac = 0.05`) and the 6-day loss window.

## Method

**"Beats the best Kelly"** = higher mean annualized return than the *best* of the 8 Kelly
variants at **each** of the 1-, 5-, 10- and 15-year horizons (the best Kelly can differ by
horizon). The margin reported is the smallest of the four differences.

**Fair premium** = total payouts ÷ insured-value-years, from one continuous policy over the
whole history with `coverage_ratio = 1` and no premium. It is what an insurer would have needed
to charge just to break even on claims, with no profit or risk loading. For coverage *c* the
fair premium is *c* × the table value.

**Screen**: 6 premiums × 4 deductibles × 3 coverage ratios = 72 variants on the S&P 500, at a
9-day start stride (3× faster than the production 3-day stride). **Confirmation**: four
representative variants re-run at the production 3-day stride on both datasets; they matched
the screen to within 0.03 points.

## Results

### Fair premium by deductible

| Deductible | S&P 500 (1956–2026) | payouts | QQQ (1999–2026) | payouts |
|---|---|---|---|---|
| 5% | 1.14%/yr | 68 | 2.85%/yr | 54 |
| 7% | 0.80%/yr | 29 | 1.56%/yr | 31 |
| 9% | 0.52%/yr | 18 | 1.33%/yr | 22 |
| 12% | 0.14%/yr | 6 | 0.29%/yr | 11 |
| 18% | 0.25%/yr | 3 | 0.24%/yr | 5 |

The 18% figure exceeds the 12% figure on the S&P 500 because of the once-per-period rule: a
smaller trigger early in a crash can use up the policy before the biggest day (e.g. October
1987). The current published premium of 1.2%/yr is ~2.3× fair at a 9% deductible and ~9× fair
at 12%.

### Screen: margin over the best Kelly variant (S&P 500, percentage points)

Smallest margin across the 1/5/10/15-year horizons; **bold** = beats the best Kelly at all four.
Benchmarks at this stride: best Kelly 8.26 / 7.33 / 7.05 / 6.95%, Buy & Hold 8.65 / 7.50 /
7.16 / 7.02% mean annualized return.

| Deductible | Coverage | 0.00% | 0.25% | 0.50% | 0.75% | 1.00% | 1.20% |
|---|---|---|---|---|---|---|---|
| 5% | 0.5 | **+0.45** | **+0.20** | -0.06 | -0.31 | -0.57 | -0.77 |
| 5% | 1.0 | **+0.89** | **+0.63** | **+0.37** | **+0.12** | -0.14 | -0.34 |
| 5% | 2.0 | **+1.75** | **+1.49** | **+1.23** | **+0.97** | **+0.72** | **+0.51** |
| 7% | 0.5 | **+0.43** | **+0.18** | -0.08 | -0.33 | -0.59 | -0.79 |
| 7% | 1.0 | **+0.83** | **+0.58** | **+0.32** | **+0.06** | -0.19 | -0.40 |
| 7% | 2.0 | **+1.62** | **+1.36** | **+1.10** | **+0.84** | **+0.59** | **+0.38** |
| 9% | 0.5 | **+0.25** | -0.01 | -0.26 | -0.52 | -0.77 | -0.97 |
| 9% | 1.0 | **+0.47** | **+0.21** | -0.05 | -0.30 | -0.56 | -0.76 |
| 9% | 2.0 | **+0.89** | **+0.64** | **+0.38** | **+0.12** | -0.13 | -0.34 |
| 12% | 0.5 | **+0.27** | **+0.01** | -0.24 | -0.50 | -0.75 | -0.96 |
| 12% | 1.0 | **+0.47** | **+0.22** | -0.04 | -0.29 | -0.55 | -0.75 |
| 12% | 2.0 | **+0.84** | **+0.58** | **+0.32** | **+0.07** | -0.19 | -0.39 |

39 of 72 variants beat the best Kelly. Each 0.25% of premium costs about 0.25 points a year:
the premium passes straight through to returns.

### Break-even premium as a multiple of fair (S&P 500)

The premium at which a variant stops beating the benchmark, interpolated from the screen.

| Deductible | Coverage | Fair premium | Break-even vs best Kelly | Break-even vs Buy & Hold |
|---|---|---|---|---|
| 5% | 0.5 | 0.57% | 0.44% (0.8×) | 0.24% (0.4×) |
| 5% | 1.0 | 1.14% | 0.86% (0.8×) | 0.67% (0.6×) |
| 5% | 2.0 | 2.28% | > 1.20% (> 0.5×) | > 1.20% (> 0.5×) |
| 7% | 0.5 | 0.40% | 0.42% (1.1×) | 0.18% (0.5×) |
| 7% | 1.0 | 0.80% | 0.81% (1.0×) | 0.55% (0.7×) |
| 7% | 2.0 | 1.59% | > 1.20% (> 0.8×) | > 1.20% (> 0.8×) |
| 9% | 0.5 | 0.26% | 0.24% (0.9×) | 0.02% (0.1×) |
| 9% | 1.0 | 0.52% | 0.46% (0.9×) | 0.23% (0.4×) |
| 9% | 2.0 | 1.04% | 0.87% (0.8×) | 0.65% (0.6×) |
| 12% | 0.5 | 0.07% | 0.26% (3.9×) | never |
| 12% | 1.0 | 0.14% | 0.46% (3.4×) | 0.13% (1.0×) |
| 12% | 2.0 | 0.27% | 0.82% (3.0×) | 0.46% (1.7×) |

### Confirmed finalists (production 3-day stride)

Mean annualized return / share of losing start dates, at 1 / 5 / 10 / 15 years.

**S&P 500**

| | Premium | Ded. | Cov. | × fair | 1y | 5y | 10y | 15y |
|---|---|---|---|---|---|---|---|---|
| Best Kelly (per horizon) | | | | | 8.28 / 24.1% | 7.33 / 10.4% | 7.05 / 3.5% | 6.95 / 0.0% |
| Buy & Hold | | | | | 8.67 / 26.7% | 7.50 / 17.7% | 7.16 / 8.4% | 7.02 / 0.0% |
| **A** market-priced | 0.40% | 12% | 1.0 | 3.0× | 8.40 / 25.4% | 7.40 / 17.5% | 7.12 / 8.3% | 7.03 / 0.0% |
| **B** fair-priced | 0.75% | 7% | 1.0 | 0.94× | 8.47 / 25.9% | 7.45 / 15.1% | 7.13 / 8.2% | 7.02 / 0.0% |
| **C** current premium, 2× cover | 1.20% | 5% | 2.0 | 0.53× | 9.03 / 24.7% | 7.92 / 12.9% | 7.59 / 5.2% | 7.46 / 0.0% |
| **D** beats Kelly on risk too | 0.25% | 7% | 2.0 | 0.16× | 9.76 / 24.0% | 8.75 / 9.0% | 8.42 / 2.8% | 8.31 / 0.0% |

**QQQ**

| | Premium | Ded. | Cov. | × fair | 1y | 5y | 10y | 15y |
|---|---|---|---|---|---|---|---|---|
| Best Kelly (per horizon) | | | | | 11.60 / 20.6% | 10.35 / 12.5% | 11.00 / 10.0% | 11.23 / 0.0% |
| Buy & Hold | | | | | 12.72 / 21.5% | 11.10 / 13.9% | 11.85 / 10.9% | 12.11 / 0.7% |
| **A** | 0.40% | 12% | 1.0 | 1.4× | 12.22 / 21.6% | 10.61 / 13.6% | 11.26 / 10.7% | 11.50 / 0.1% |
| **B** | 0.75% | 7% | 1.0 | 0.48× | 13.39 / 20.7% | 11.40 / 12.0% | 11.89 / 8.4% | 12.12 / 0.0% |
| **C** | 1.20% | 5% | 2.0 | 0.21× | 17.50 / 17.4% | 14.92 / 5.7% | 15.53 / 2.5% | 15.61 / 0.0% |
| **D** | 0.25% | 7% | 2.0 | 0.08× | 16.10 / 18.3% | 13.40 / 6.8% | 13.67 / 3.2% | 13.89 / 0.0% |

All four beat the best Kelly at every horizon on both datasets.

## How practical are these parameters?

| | Verdict | Why |
|---|---|---|
| **A** | Realistic price, no benefit | Priced like real crash protection (premium ~1.5–3× expected payouts), but it is Buy & Hold with a small drag: it trails Buy & Hold at every horizon on QQQ and at 1–10 years on the S&P 500 (tying at 15), and does not reduce losing start dates. |
| **B** | Not offered | At fair value on the S&P 500 and half of fair on QQQ, the seller earns nothing or loses money. |
| **C** | Not insurance | Coverage 2.0 pays twice the loss beyond the deductible — a leveraged crash bet — and is priced at 21–53% of its historical cost. The large QQQ gains come from buying 5.7%/yr of protection for 1.2%. |
| **D** | Not offered | The only setting that also beats Kelly on losing start dates, at 8–16% of its historical cost. |

Other practical limits:

- **No such contract exists.** The policy pays on any 6-day drop past the deductible, measured
  from a rolling window. The closest real instrument is a continuously rolled ladder of
  short-dated out-of-the-money index puts, which has generally cost more than its realized
  payouts (option sellers are paid a premium for bearing crash risk).
- **Hindsight.** Fair premiums are measured on the same history the backtest uses. QQQ's 26
  years are dominated by 2000–02 and 2008, so its fair premiums are especially fragile.
- **Not modeled**: transaction costs, bid/ask spreads on protection, counterparty risk in a
  crash, and taxes.

## Conclusion

Crash insurance in this model is close to a zero-sum transfer: whatever it beats Kelly by, it
gets from buying protection at or below its historical cost. At any price a seller would
charge, the insured portfolio is Buy & Hold minus the premium. If insurance variants are kept
in the grid, their premiums should be set as a loading over each deductible's fair premium
(e.g. 1.5–3×) rather than one flat rate, so the comparison stays honest.

## Reproduce

```bash
S=notebooks/insurance_scan
poetry run python $S/fair_premium.py sp500 qqq                           # fair premium table
poetry run python $S/sweep.py screen sp500 9 $S/screen_sp500.json        # 72-variant screen (~20 min, 24 cores)
poetry run python $S/sweep.py $S/finalists.json sp500 3 $S/final_sp500.json
poetry run python $S/sweep.py $S/finalists.json qqq 3 $S/final_qqq.json
poetry run python $S/analyze.py $S/screen_sp500.json 40                  # ranked table
```
