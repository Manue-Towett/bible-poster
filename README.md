# bible-poster
Posts html files to https://bsi.driftingkelp.com/

# Settings
Use settings.ini file in settings directory to configure the login credentials, threads number, start url, english bible category

# Usage
Requires python 3.10+

Open the terminal

change terminal's directory into the project directory

If running for the first time, install dependencies using the command:

```pip install -r requirements.txt```

Run the script using the command:

For linux/mac:

    Update:
        python3 post.py -i <input path> --update e.g python3 post.py -i ./input/ --update
    
    Without updating:
        eg python3 post.py -i ./input/ 

For windows:

    Update:
        python post.py -i <input path> --update e.g python post.py -i ./input/ --update
    
    Without updating:
        eg python post.py -i ./input/ 