import sys
##########################################################################################################
# https://seekingalpha.com/symbol/SP500/historical-price-quotes
# cut and paste new records to text file
# run transform_new_sp500_records.py:
#     cat deleteme.csv | python bin/transform_new_sp500_records.py | xclip -sel clip
# prepend to the sp500.tab file
##########################################################################################################
out = []
for i, line in enumerate(sys.stdin):
    out.append(line.strip())
    if (i+1)%3 == 0:
        out[0] = out[0].replace(".","")
        adj = out[1].split("\t")[3]
        out[1] += "\t" + adj 
        print("\t".join(out))
        out = []

