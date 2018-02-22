## Draw Mempool !

A tool to draw and inspect mempool transactions and their dependencies. This currently
requires a locally running version of bitcoind and will use `bitcoin-cli` to poll
for mempool info and block template info.


This is a total WIP and may (probably) contain bugs.



### Installation Ubuntu & Debian
```
sudo apt-get install python3-tk tk-dev graphviz graphviz-dev
virtualenv -p /usr/bin/python3 .venv
source .venv/bin/activate
pip install -r requirement.txt
```

### Installion Mac / Windows
TODO

### Try it out
```
./draw_mempool.py --help
```

### Examples
```
# Only show transactions with dependencies
./draw_mempool.py --minancestors=2 --minfeerate=20 --maxage=60  

# Show high fee transactions
./draw_mempool.py --minfeerate=500

# Animate live mempool, coloring tx's to be included in next block as blue
./draw_mempool.py --maxage=10 --animate --colorbt
```

### TODO
- Switch to logging
- Make verticle line on X-axis for when blocks were produced
- Make conf file
- Event click on descendant lines to highlight dependency chain
- Highlight RBF and CPFP candidates
- Ability to toggle/subtract getblocktemplate from mempool
- Add horizontal lines for estimated fee / per confirmation window
- Calculate optimal blockfee based on mempool graph and compare to getblocktemplate

### Donations

BTC: 1NoZkz1neig1DtDy6etwYB9fgHqEv3oesG

BTC (Bech32): bc1q52ru4udqk9nnqz4hcg7ukq0wruld6hny43xjj3

