A tool to draw and inspect mempool transactions and their dependencies 

This is a total WIP and probably will not work as expected.

#### TODO
- Make verticle line for when block was produced
- Make conf file
- Event click on line
- Highlight RBF and CPFP candidates
- Subtract getblocktemplate from mempool
- Calculate optimal blockfee based on mempool graph and compared to getblocktemplate

#### Installation
```
sudo apt-get install python3-tk tk-dev graphviz graphviz-dev
virtualenv -p /usr/bin/python3 .venv
source .venv/bin/activate
pip install -r requirement.txt
```

#### Try it out
```
./draw_mempool.py --help
```

#### Examples
```
./draw_mempool.py --minancestors=2 --minfeerate=20 --maxage=60  # Show related transactions
./draw_mempool.py --minsize=500 --minfee=500  # Show big transactions
./draw_mempool.py --maxage=10 --animate --colorbt   # Animate tranactions coming in
```
