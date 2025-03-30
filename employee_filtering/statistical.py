import pandas as pd
import json

def stat_select(json_file):
    def json_to_dataframes(employee_data):
        # Initialize datasets dictionary
        datasets = {"activity": [], "leave": [], "onboarding": [], "performance": [], "rewards": [], "vibemeter": []}
        # Loop through each employee entry in JSON
        for emp_entry in employee_data:
            emp_id = emp_entry["employee_id"]
            company_data = emp_entry["company_data"]

            # Recreate datasets
            for dataset_name, records in company_data.items():
                for record in records:
                    record["Employee_ID"] = emp_id  # Add Employee_ID back
                    datasets[dataset_name].append(record)

        # Convert lists to DataFrames
        for dataset_name in datasets:
            datasets[dataset_name] = pd.DataFrame(datasets[dataset_name])

        return datasets

    dfs = json_to_dataframes(json_file)

    datasets = ["activity", "leave", "onboarding", "performance", "rewards", "vibemeter"]

    arr = []
    for name in datasets:
        df = dfs[name]
        filtered_ids = df['Employee_ID'].value_counts()
        filtered_ids = filtered_ids[filtered_ids >= filtered_ids.quantile(0.99)].index
        arr = arr + filtered_ids.tolist()

    return list(set(arr))