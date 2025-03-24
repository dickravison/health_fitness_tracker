# health_fitness_tracker

This is used to export health and training data from intervals.icu and import it into DynamoDB. This will also send a notification at the start of the week and start of the month containing statistics, such as difference in weight, amount of training complete, any PBs. There is also a function that sends a personalised nutrition plan for the upcoming planned week of training.

## Getting Started
Create the `env/` directory under `tf/`. In here you should add your input variables into a .tfvars file and your backend config in a .hcl file. You then can start deploying by using:

```
tofu init -backend-config=env/dev.hcl -var-file=env/dev.tfvars
```

The service can then be deployed using:

```
tofu plan -var-file=env/dev.tfvars
tofu apply -var-file=env/dev.tfvars
```

This will not work until the two parameters in Parameter Store are updated with the correct values (your UID and API key from intervals.icu). When they are deployed, they are deployed with the value 'PLACEHOLDER' so that they are not stored in state in plain text.

Notifications are sent using SNS.

## Lambda Functions

### Export
The export function pulls data from intervals.icu into AWS. This runs each night and pulls in the past 7 days of data by default. For the initial import, the `FULL_IMPORT` variable can be set to true to import all data (this defaults to 2010-01-01 so if you have any data from before then, this would need to be updated) from intervals.icu.

### Notify
The notify function generates statistics from the data on both a weekly and monthly frequency. It will compare the previous period with the current period (the previous week and the week previous to that, the previous month and the month previous to that). It will also collate the PBs that have been achieved during that period. A message designed for the Pushover notification service is then published to an SNS topic (which in my case, then sends it to Pushover).

### Nutrition
The nutrition function generates a personalised periodised nutrition plan. It runs on a Monday morning and uses the upcoming week of planned sessions. The personalised nutrition plan is adapted from the work by Alan Couzens which can be found [here](https://alancouzens.substack.com/p/chapter-15-fueling-the-work-high). This is reliant on the intensity being provided by the planned session and will not work without it. This should be automatically calculated as long as the planned workout has sufficient data. There are some variables that need to be set here which are:

- `WEIGHT_LOSS` - boolean to determine if a calorie deficit should be applied
- `ACTIVITY_LEVEL` - the activity level of the user, look at the `ACTIVITY_MULTIPLIERS` variable to see how this affects the total calories
- `HEIGHT` - the users height
- `TT_100M_SECS` - the users 100M swim time trial in secs
- `SWIM_LEVEL` - the users level of swimming, please read [here](https://alancouzens.blogspot.com/2010/01/are-you-skilled-swimmer.html)

There is also a limit of how low the calories can go which is controlled by the `CALORIE_FLOOR` variable, with a default setting as 1600.