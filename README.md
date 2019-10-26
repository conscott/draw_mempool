## Bitcoin Mempool Inspector

A tool to inspect and filter mempool transactions and their dependencies. This currently
requires a locally running version of bitcoind and will use `bitcoin-cli` to pull
data about the mempool and block template info.

### Requirements

* Bitcoin Core >= v0.17
* Python >= 3.4
* TK for Python: `sudo apt-get install python3-tk`

### Installation Ubuntu & Debian

To Install With `pip`
```
pip3 install draw_mempool
```

To Install from Source
```
git clone https://github.com/conscott/draw_mempool
cd draw_mempool
python3 -v venv venv
source venv/bin/activate
python3 setup.py install
```

### Try it out
```
./draw_mempool.py --help
```

### Examples
```
# Only show transactions with ancestor dependencies within last 60 minutes with a fee-rate
# above 20 sat/byte
./draw_mempool.py --minancestors=2 --minfeerate=20 --maxage=60  

# Show high fee transactions (above 300 sat/byte)
./draw_mempool.py --minfeerate=300

# Animate live mempool, coloring tx's to be included in next block as blue
./draw_mempool.py --maxage=10 --animate --color_bt

# Color transactions signaling RBF
./draw_mempool.py --color_rbf 

# Draw the 2-block fee estimate as a horizontal line, as well as coloring 
# transactions to be included in the next block
./draw_mempool.py --nestimatefee=2 --color_bt
```

### Events
- Clicking on a tx will print the tx hash and fee / size information. 
- Double clicking on a transactions will open a browser tab, to inspect the tx on blockstream.info
- Clicking the 'm' button will redraw the mempool without the txs included in `getblocktemplate`, to help visualize what the mempool would look like after the next block is mined (can help with fee estimates). 
- You can zoom and pan using the buttons provided in the lower menu.

### Known Issues
- This program gets quite slow when there is a large mempool and does best when there are less than 10,000 transactions to draw. You can use the tx filter functions (like `--maxage`) to reduce the total txs drawn.
- When using `--animate`, the zoom will reset on every re-draw.
