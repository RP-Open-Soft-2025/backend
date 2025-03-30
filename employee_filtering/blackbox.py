import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from collections import Counter
from scipy import stats
import json

def select_employees(json_data):
    def extract_employee_features(employee_json_data):

        processed_data = []

        for employee in employee_json_data:
            employee_id = employee.get('employee_id')
            if not isinstance(employee_id, str) or not employee_id.strip():
                print(f"Warning: Invalid or missing employee_id, skipping record -> {employee}")
                continue  # Skip if employee_id is missing or invalid

            # Extract `company_data` (should be a dictionary)
            company_data = employee.get('company_data', {})
            if not isinstance(company_data, dict):
                print(f"Warning: `company_data` should be a dictionary, skipping record for {employee_id}.")
                continue  # Skip this entry

            # Initialize feature dictionary
            features = {'employee_id': employee_id}

            # Process leave data
            leave_days = sum(leave.get('Leave_Days', 0) for leave in company_data.get('leave', []) if isinstance(leave, dict))
            features['total_leave_days'] = leave_days

            # Process performance data
            performance_ratings = [p.get('Performance_Rating', 0) for p in company_data.get('performance', []) if isinstance(p, dict)]
            features['average_performance_rating'] = np.mean(performance_ratings) if performance_ratings else 0
            features['performance_review_count'] = len(performance_ratings)

            # Process rewards data
            rewards = company_data.get('rewards', [])
            total_reward_points = sum(reward.get('Reward_Points', 0) for reward in rewards if isinstance(reward, dict))
            features['total_reward_points'] = total_reward_points

            # Process vibe scores
            vibe_scores = [vibe.get('Vibe_Score', 0) for vibe in company_data.get('vibemeter', []) if isinstance(vibe, dict)]
            features['average_vibe_score'] = np.mean(vibe_scores) if vibe_scores else 0
            features['vibe_response_count'] = len(vibe_scores)

            # Append extracted features to processed data list
            processed_data.append(features)

        # Convert processed data into a DataFrame
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


