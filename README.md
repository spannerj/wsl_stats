# WSL stats
A collection of wsl stats for fantasy football collected from [Aerial Fantasy Football](https://www.aerialfantasy.co/)

## Process
There is a 3 stage process.

#### Extract
Run ```python extract.py``` to scrape the Aerial website. This will produce a file called ```data.json``` for use in the next step.

### Transform
Run ```python transform.py``` to transform the data scraped from the website into a format fit for a data table. The transform will also calculate some stats to help fantasy players. The data is output into a ```transformed_data.json``` file for use in the next step.

### Load
To 'Load' the data it will need to be checked into Github where the Git Pages action will run and host a webpage containing the data table. There is an ```index.html``` file which uses the data from the ```transformed_data.json``` file to populate the table.

### Testing
You can run the scripts locally to generate the json files and run a local webserver to see the results using ```https://spannerj.github.io/wsl_stats/```

Simply create a virtual env - ```python -m venv .venv```

Activate the environment - ```source .venv/bin/activate```

Install requirements - ```pip install -r requirements.txt```
