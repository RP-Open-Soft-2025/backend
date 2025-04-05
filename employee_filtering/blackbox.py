import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from collections import Counter
# from scipy import stats
# import json

def select_employees(json_data):
    
    def extract_employee_features(employee_json_data):

        processed_data = []

        for employee in employee_json_data:
            employee_id = employee.get('employee_id')
            if not isinstance(employee_id, str) or not employee_id.strip():
                print(f"Warning: Invalid or missing employee_id, skipping record -> {employee}")
                continue  # Skip if employee_id is missing or invalid

            company_data = employee.get('company_data', {})
            if not isinstance(company_data, dict):
                print(f"Warning: `company_data` should be a dictionary, skipping record for {employee_id}.")
                continue  # Skip this entry

            features = {'employee_id': employee_id}

            def parse_date(date_str):
                if "H2" in date_str or "H1" in date_str:
                    # Handling half-year formats like 'H2 2023'
                    return pd.to_datetime(date_str.replace("H2", "12").replace("H1", "06"), format="%m %Y", errors="coerce")
                return pd.to_datetime(date_str, errors="coerce")

            def calculate_ema(data, date_key, value_key):
                if not data:
                    return 0
                sorted_data = sorted(data, key=lambda x: parse_date(x.get(date_key, '')))
                ema_value = 0
                alpha = 0.1  # smoothing factor for EMA
                for i, entry in enumerate(sorted_data):
                    value = entry.get(value_key, 0)
                    date_value = parse_date(entry.get(date_key, ''))
                    if pd.isna(date_value):
                        continue
                    if i == 0:
                        ema_value = value
                    else:
                        time_diff = (date_value - parse_date(sorted_data[i - 1].get(date_key, ''))).days / 30.0
                        dynamic_alpha = alpha / (1 + time_diff)
                        ema_value = dynamic_alpha * value + (1 - dynamic_alpha) * ema_value
                return ema_value

            leave_data = company_data.get('leave', [])
            features['total_leave_days'] = calculate_ema(leave_data, 'Leave_End_Date', 'Leave_Days')

            activity_data = company_data.get('activity', [])
            features['average_teams_messages_sent'] = calculate_ema(activity_data, 'Date', 'Teams_Messages_Sent')
            features['average_emails_sent'] = calculate_ema(activity_data, 'Date', 'Emails_Sent')
            features['average_work_hours'] = calculate_ema(activity_data, 'Date', 'Work_Hours')
            features['total_meetings_attended'] = calculate_ema(activity_data, 'Date', 'Meetings_Attended')

            performance_data = company_data.get('performance', [])
            features['average_performance_rating'] = calculate_ema(performance_data, 'Review_Period', 'Performance_Rating')

            rewards_data = company_data.get('rewards', [])
            features['total_reward_points'] = calculate_ema(rewards_data, 'Award_Date', 'Reward_Points')

            vibemeter_data = company_data.get('vibemeter', [])
            features['average_vibe_score'] = calculate_ema(vibemeter_data, 'Response_Date', 'Vibe_Score')

            processed_data.append(features)

        return pd.DataFrame(processed_data)


    def json_anomaly_detection(employee_json_data, contamination=0.05):

        df = extract_employee_features(employee_json_data)

        if df.empty:
            return pd.DataFrame()

        employee_ids = df['employee_id']
        df = df.drop('employee_id', axis=1)

        df.fillna(0, inplace=True)

        numerical_cols = df.select_dtypes(include=['int64', 'float64']).columns.tolist()

        # Step 3: Apply preprocessing for other models
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', StandardScaler(), numerical_cols) if numerical_cols else ('pass', 'passthrough', [])
            ],
            remainder='passthrough'
        )

        # Apply preprocessing
        X_processed = preprocessor.fit_transform(df)

        # Step 4: Apply Isolation Forest
        iso_forest = IsolationForest(contamination=contamination, random_state=42)
        iso_forest.fit(X_processed)
        scores_if = -iso_forest.score_samples(X_processed)

        # Step 5: Apply Local Outlier Factor if we have enough samples
        if len(df) > 5:
            n_neighbors = min(10, len(df) - 1)
            lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
            lof.fit(X_processed)
            scores_lof = -lof.negative_outlier_factor_
        else:
            scores_lof = np.zeros_like(scores_if)

        # Normalize scores to [0, 1]
        def normalize(scores):
            if np.max(scores) - np.min(scores) == 0:
                return np.zeros_like(scores)
            return (scores - np.min(scores)) / (np.max(scores) - np.min(scores))

        scores_if_norm = normalize(scores_if)
        scores_lof_norm = normalize(scores_lof)

        # Ensemble score: weighted average of normalized scores
        ensemble_scores = (scores_if_norm + scores_lof_norm ) / 2

        # Threshold based on contamination parameter
        threshold = np.percentile(ensemble_scores, 100 * (1 - contamination))

        # Results DataFrame with anomaly detection results
        result_df = pd.DataFrame({
            'employee_id': employee_ids,
            'anomaly_score': ensemble_scores,
            'needs_counseling': ensemble_scores > threshold,
            'isolation_forest_score': scores_if_norm,
            'lof_score': scores_lof_norm,
        })

        return result_df.sort_values('anomaly_score', ascending=False)

    results_df = json_anomaly_detection(json_data, contamination=0.1)
    selected_employees = results_df[results_df['needs_counseling'] == True]['employee_id'].values.tolist()
    return selected_employees


