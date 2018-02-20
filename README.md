A tool to draw and inspect mempool transactions and their dependencies 

This is a total WIP and probably will not work as expected.

#### TODO
- Make conf file
- Animations
- Event click on line
- URL picking

#### Installation
```
sudo apt-get install python3-tk tk-dev graphviz graphviz-dev
virtualenv -p /usr/bin/python3 .venv
source .venv/bin/activate
pip install -r requirement.txt
```

#### Try it out
```
./draw_mempool.py
```
