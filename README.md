# Rainbow

*a python library for parsing chromatography data*

by Eugene Kwan and Evan Shi

## Setup

Clone the repository and enter the main directory.
```
git clone https://github.com/evanyeyeye/rainbow.git
cd rainbow
```

Create and activate a virtual environment. 
```
virtualenv venv
source venv/bin/activate
```

Install the required dependencies.
```
pip install -r requirements.txt
```

Update your PYTHONPATH by adding this line to your .bash_profile or .bashrc file. 
```
export PYTHONPATH="$PYTHONPATH:(YOUR CURRENT WORKING DIRECTORY)"
```

## Testing

```
cd test
python test_agilent.py
```

## Docs

```
cd docs
make html
```

The docpages are generated under the docs/_build directory. 
