"""
Alert service for AIND Dashboard

This module provides services for managing and calculating alerts based on percentile rankings.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app_utils.simple_logger import get_logger


class AlertService:
    """
    Service for getting / setting alerts based on percentile rankings
    """

    # Default percentile category boundaries
    DEFAULT_PERCENTILE_CATEGORIES = {
        "SB": 6.5,  # Significantly Bad: < 6.5% ( < -2.75 std dev)
        "B": 28,  # Bad: < 28% ( < -0.25 std dev)
        "N": 72,  # Normal: 28% - 72% ( -0.25 std dev to +0.25 std dev)
        "G": 93.5,  # Good: 72% - 93.5% ( > +0.25 std dev)
        "SG": 100,  # Significantly Good: > 93.5% ( > +2.75 std dev)
    }

    # Default minimum sessions for eligibility
    DEFAULT_MIN_SESSIONS = 1

    def __init__(self, app_utils=None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the AlertService

        Parameters:
            app_utils (AppUtils): The AppUtils instance (optional)
            config (Dict[str, Any]): Optional configuration for the AlertService
        """
        self.app_utils = app_utils
        self.logger = get_logger("alerts")

        # Initialize configuation with default
        self.config = {
            "percentile_categories": self.DEFAULT_PERCENTILE_CATEGORIES.copy(),
            "feature_config": {},  # Feature specific configuration
            "min_sessions": self.DEFAULT_MIN_SESSIONS,
        }

        # Override defaults if provided with config
        if config:
            self._update_config(config)

        # Initialize alert caches
        self._quantile_alerts = {}

    def _update_config(self, config: Dict[str, Any]) -> None:
        """
        Update the configuration with new values

        Parameters:
            config (Dict[str, Any]): The new configuration
        """
        if "percentile_categories" in config:
            # Merge with defaults
            self.config["percentile_categories"].update(config["percentile_categories"])

        if "feature_config" in config:
            self.config["feature_config"].update(config["feature_config"])

    def map_percentile_to_category(self, percentile: float) -> str:
        """
        Map a percentile value to its corresponding category

        Parameters:
            percentile (float): The percentile value to map

        Returns:
            str: Category abbreviation (SB, B, N, G, SG)
        """
        if percentile is None or np.isnan(percentile):
            return "Unknown"

        categories = self.config["percentile_categories"]

        if percentile < categories["SB"]:
            return "SB"
        elif percentile < categories["B"]:
            return "B"
        elif percentile < categories["N"]:
            return "N"
        elif percentile < categories["G"]:
            return "G"
        else:
            return "SG"

    def get_category_description(self, category: str) -> str:
        """
        Get the description for a given category

        Parameters:
            category (str): The category abbreviation (SB, B, N, G, SG)

        Returns:
            str: Description of the category
        """
        descriptions = {
            "SB": "Significantly Below Average",
            "B": "Below Average",
            "N": "Average",
            "G": "Above Average",
            "SG": "Significantly Above Average",
        }
        return descriptions.get(category, "Unknown")

    def _validate_analyzer(self) -> bool:
        """
        Validate that required analyzers are available

        Returns:
            bool: True if all required analyzers are available
        """
        if self.app_utils is None:
            return False

        # Check quantile analyzer and percentile calculator
        has_quantile = (
            hasattr(self.app_utils, "quantile_analyzer")
            and self.app_utils.quantile_analyzer is not None
        )
        has_calculator = (
            hasattr(self.app_utils, "percentile_calculator")
            and self.app_utils.percentile_calculator is not None
        )

        return has_quantile and has_calculator

    def calculate_quantile_alerts(
        self, subject_ids: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calculate quantile-based alerts for subjects using session-level data

        Parameters:
            subject_ids: Optional[List[str]]
                List of subject IDs to calculate alerts for

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping subject IDs to their quantile alerts
        """
        # Make sure we have the quantile analyzer
        if not self._validate_analyzer():
            return {}

        # Get session-level overall percentiles using the new approach
        session_percentiles = self.app_utils.get_session_overall_percentiles(
            subject_ids=subject_ids
        )

        # Create a dictionary to store alerts by subject ID
        alerts = {}

        # Process each subject's most recent session
        for _, row in session_percentiles.iterrows():
            subject_id = row["subject_id"]

            # Extract overall percentile from session data
            overall_percentile = row.get("session_overall_percentile")

            # Skip subjects with no percentile (not scored)
            if pd.isna(overall_percentile):
                # Get reason for not scored
                ns_reason = self.get_not_scored_reason(subject_id)

                # Create alert with not scored status
                alerts[subject_id] = {
                    "subject_id": subject_id,
                    "overall_percentile": None,
                    "alert_category": "NS",
                    "ns_reason": ns_reason,
                    "strata": row.get("strata", "Unknown"),
                }
                continue

            # Map percentile to category using configured thresholds
            alert_category = self.map_percentile_to_category(overall_percentile)

            # Create alert
            alerts[subject_id] = {
                "subject_id": subject_id,
                "overall_percentile": overall_percentile,
                "alert_category": alert_category,
                "strata": row.get("strata", "Unknown"),
            }

            # Add feature-specific percentiles from session data
            feature_percentiles = {}
            for feature in [
                "finished_trials",
                "ignore_rate",
                "total_trials",
                "foraging_performance",
                "abs(bias_naive)",
            ]:
                session_percentile_col = f"{feature}_session_percentile"

                # Check if feature percentile is in the session data
                if session_percentile_col in row and not pd.isna(
                    row[session_percentile_col]
                ):
                    feature_percentile = row[session_percentile_col]
                    feature_category = self.map_percentile_to_category(
                        feature_percentile
                    )

                    # Add to feature percentiles
                    feature_percentiles[feature] = {
                        "percentile": feature_percentile,
                        "category": feature_category,
                    }

            # Add feature percentiles to alert
            if feature_percentiles:
                alerts[subject_id]["feature_percentiles"] = feature_percentiles

        # Store alerts for later retrieval
        self._quantile_alerts = alerts

        # Return alerts dictionary
        return alerts

    def get_quantile_alerts(
        self, subject_ids: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get precomputed quantile alerts for specified subjects

        Parameters:
            subject_ids: Optional[List[str]]
                List of subject IDs to get alerts for

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping subject IDs to their quantile alerts
        """
        # Validate that we have an analyzer
        if not self._validate_analyzer():
            return {}

        # Calculate alerts if not already calculated
        if not hasattr(self, "_quantile_alerts") or self._quantile_alerts is None:
            self.calculate_quantile_alerts()

        # Return all alerts if no subject IDs specified
        if subject_ids is None:
            return self._quantile_alerts

        # Otherwise, filter alerts for specified subjects
        result = {}
        for subject_id in subject_ids:
            if subject_id in self._quantile_alerts:
                result[subject_id] = self._quantile_alerts[subject_id]

        return result

    def map_overall_percentile_to_category(self, overall_percentile):
        """
        Map an overall percentile to its corresponding category

        Parameters:
            overall_percentile (float): The overall percentile value to map

        Returns:
            str: Category abbreviation (SB, B, N, G, SG)
        """
        if overall_percentile is None or np.isnan(overall_percentile):
            return "NS"  # Not scored

        categories = self.config["percentile_categories"]

        if overall_percentile < categories["SB"]:
            return "SB"
        elif overall_percentile < categories["B"]:
            return "B"
        elif overall_percentile < categories["N"]:
            return "N"
        elif overall_percentile < categories["G"]:
            return "G"
        else:
            return "SG"

    def get_not_scored_reason(self, subject_id: str) -> str:
        """
        Get the reason why a subject is not scored (NS)

        Parameters:
            subject_id (str): The subject ID to check

        Returns:
            str: Reason why the subject is not scored
        """
        try:
            if self.app_utils is None:
                return "No app_utils available"

            # Get session data for this subject
            session_data = self.app_utils.get_session_data(use_cache=True)
            if session_data.empty:
                return "No session data"

            # Filter for this subject
            subject_sessions = session_data[session_data["subject_id"] == subject_id]
            if subject_sessions.empty:
                return "Subject not found"

            # Check session count requirements
            session_count_reason = self._check_session_count_requirements(
                subject_sessions
            )
            if session_count_reason:
                return session_count_reason

            # Check trial requirements
            trial_reason = self._check_trial_requirements(subject_sessions)
            if trial_reason:
                return trial_reason

            # Check feature availability
            feature_reason = self._check_feature_availability(subject_sessions)
            if feature_reason:
                return feature_reason

            # Default reason
            return "Scoring criteria not met"

        except Exception as e:
            return f"Error determining reason: {str(e)}"

    def _check_session_count_requirements(
        self, subject_sessions: pd.DataFrame
    ) -> Optional[str]:
        """Check if subject has sufficient sessions for scoring"""
        total_sessions = len(subject_sessions)
        min_sessions = self.config.get(
            "min_sessions_for_scoring", self.DEFAULT_MIN_SESSIONS
        )

        if total_sessions < min_sessions:
            return f"Insufficient sessions: {total_sessions} < {min_sessions}"
        return None

    def _check_trial_requirements(
        self, subject_sessions: pd.DataFrame
    ) -> Optional[str]:
        """Check if subject has sufficient trials for scoring"""
        most_recent = subject_sessions.sort_values(
            "session_date", ascending=False
        ).iloc[0]
        finished_trials = most_recent.get("finished_trials")

        if pd.isna(finished_trials) or finished_trials == 0:
            return "No finished trials"
        return None

    def _check_feature_availability(
        self, subject_sessions: pd.DataFrame
    ) -> Optional[str]:
        """Check if required features are available for scoring"""
        most_recent = subject_sessions.sort_values(
            "session_date", ascending=False
        ).iloc[0]
        required_features = ["total_trials", "finished_trials", "ignore_rate"]
        missing_features = []

        for feature in required_features:
            if pd.isna(most_recent.get(feature)):
                missing_features.append(feature)

        if missing_features:
            return f"Missing features: {', '.join(missing_features)}"
        return None

    def filter_by_threshold_alerts(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter dataframe to show only subjects with threshold alerts

        Parameters:
            df (pd.DataFrame): DataFrame to filter for threshold alerts

        Returns:
            pd.DataFrame: Filtered DataFrame containing only subjects with threshold alerts
        """
        if df.empty:
            return df

        # Generate threshold alert mask using the extracted logic
        threshold_mask = self.get_alert_category_mask(df, "T")

        # Apply the mask and log results
        before_count = len(df)
        filtered_df = df[threshold_mask]
        after_count = len(filtered_df)

        self.logger.info(
            f"Threshold filter applied: {before_count} → {after_count} subjects"
        )

        return filtered_df

    def validate_alert_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Validate and debug alert patterns in dataframe

        Parameters:
            df (pd.DataFrame): DataFrame to validate alert patterns for

        Returns:
            Dict[str, Any]: Validation results including value counts and quality metrics
        """
        validation_results = {
            "total_subjects": len(df),
            "value_counts": {},
            "missing_columns": [],
            "quality_metrics": {},
        }

        # Expected alert columns for validation
        alert_columns = [
            "threshold_alert",
            "total_sessions_alert",
            "stage_sessions_alert",
            "water_day_total_alert",
        ]

        # Check each alert column and gather value counts
        for col in alert_columns:
            if col in df.columns:
                # Get value counts for this column
                value_counts = df[col].value_counts()
                validation_results["value_counts"][col] = value_counts.to_dict()

                # Calculate quality metrics
                total_values = len(df)
                missing_values = df[col].isna().sum()

                validation_results["quality_metrics"][col] = {
                    "total_values": total_values,
                    "missing_values": missing_values,
                    "missing_percentage": (
                        (missing_values / total_values * 100) if total_values > 0 else 0
                    ),
                    "unique_values": df[col].nunique(),
                }
            else:
                validation_results["missing_columns"].append(col)

        # Analyze threshold patterns specifically
        threshold_patterns = self._analyze_threshold_patterns(df)
        validation_results["threshold_patterns"] = threshold_patterns

        return validation_results

    def get_alert_category_mask(
        self, df: pd.DataFrame, alert_category: str
    ) -> pd.Series:
        """
        Generate boolean mask for specific alert category filtering

        Parameters:
            df (pd.DataFrame): DataFrame to generate mask for
            alert_category (str): Alert category ('T', 'NS', 'B', 'G', 'SB', 'SG')

        Returns:
            pd.Series: Boolean mask for filtering the dataframe
        """
        if df.empty:
            return pd.Series([], dtype=bool)

        if alert_category == "T":
            # Complex threshold alert pattern matching
            threshold_mask = (
                # Overall threshold alert column set to 'T'
                (df.get("threshold_alert", pd.Series(dtype="object")) == "T")
                # Individual threshold alerts contain "T |" pattern
                | (
                    df.get(
                        "total_sessions_alert", pd.Series(dtype="object")
                    ).str.contains(r"T \|", na=False)
                )
                | (
                    df.get(
                        "stage_sessions_alert", pd.Series(dtype="object")
                    ).str.contains(r"T \|", na=False)
                )
                | (
                    df.get(
                        "water_day_total_alert", pd.Series(dtype="object")
                    ).str.contains(r"T \|", na=False)
                )
            )
            return threshold_mask

        elif alert_category == "NS":
            # Not Scored subjects - use the correct column name
            percentile_col = (
                "overall_percentile_category"
                if "overall_percentile_category" in df.columns
                else "percentile_category"
            )
            return df[percentile_col] == "NS"

        else:
            # Percentile category filtering (B, G, SB, SG)
            percentile_col = (
                "overall_percentile_category"
                if "overall_percentile_category" in df.columns
                else "percentile_category"
            )
            return df[percentile_col] == alert_category

    def _analyze_threshold_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Private method to analyze threshold patterns in the dataframe

        Parameters:
            df (pd.DataFrame): DataFrame to analyze

        Returns:
            Dict[str, Any]: Analysis results for threshold patterns
        """
        analysis = {
            "exact_matches": 0,
            "pattern_matches": {},
            "total_threshold_subjects": 0,
        }

        # Count exact matches (threshold_alert == 'T')
        if "threshold_alert" in df.columns:
            analysis["exact_matches"] = (df["threshold_alert"] == "T").sum()

        # Count pattern matches for each alert type
        alert_columns = [
            "total_sessions_alert",
            "stage_sessions_alert",
            "water_day_total_alert",
        ]

        for col in alert_columns:
            if col in df.columns:
                pattern_matches = df[col].str.contains(r"T \|", na=False).sum()
                analysis["pattern_matches"][col] = pattern_matches

        # Calculate total subjects with any threshold alert
        mask = self.get_alert_category_mask(df, "T")
        analysis["total_threshold_subjects"] = mask.sum()

        return analysis

    def get_unified_alerts(self, subject_ids=None):
        """
        Get unified alert structure combining both quantile and threshold alerts

        Parameters:
            subject_ids (Optional[List[str]]): List of subject IDs to get alerts for

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping subject IDs to their unified alerts
        """
        # Validate analyzer requirements
        if not self._validate_analyzer():
            raise ValueError(
                "Required analyzers not available. Initialize with AppUtils instance."
            )

        # Get quantile alerts
        quantile_alerts = self.get_quantile_alerts(subject_ids)

        # Get threshold alerts
        threshold_alerts = self._get_threshold_alerts()

        # Get all subjects to process
        all_subjects = self._determine_all_subjects(
            subject_ids, quantile_alerts, threshold_alerts
        )

        # Initialize unified alerts structure
        unified_alerts = {}

        # Handle off-curriculum subjects
        self._handle_off_curriculum_subjects(all_subjects, unified_alerts)

        # Process quantile and threshold alerts
        self._process_quantile_and_threshold_alerts(
            quantile_alerts, threshold_alerts, unified_alerts
        )

        # Add feature-specific percentiles
        self._add_feature_percentiles(unified_alerts, subject_ids)

        # Calculate and add overall percentiles
        self._add_overall_percentiles(all_subjects, unified_alerts)

        # Handle subjects without alerts
        self._handle_subjects_without_alerts(all_subjects, unified_alerts)

        return unified_alerts

    def _get_threshold_alerts(self) -> Dict[str, Any]:
        """Get threshold alerts if threshold analyzer is available"""
        threshold_alerts = {}

        if (
            hasattr(self.app_utils, "threshold_analyzer")
            and self.app_utils.threshold_analyzer is not None
            and hasattr(self.app_utils, "get_session_data")
        ):
            df = self.app_utils.get_session_data()
            threshold_df = self.app_utils.threshold_analyzer.analyze_thresholds(df)
            most_recent = (
                threshold_df.sort_values("session_date")
                .groupby("subject_id")
                .last()
                .reset_index()
            )
            threshold_alerts = self._process_threshold_alerts(most_recent)

        return threshold_alerts

    def _process_threshold_alerts(self, most_recent_df: pd.DataFrame) -> Dict[str, Any]:
        """Process threshold alerts from most recent session data"""
        threshold_alerts = {}
        stage_thresholds = {
            "STAGE_1": 5,
            "STAGE_2": 5,
            "STAGE_3": 6,
            "STAGE_4": 10,
            "STAGE_FINAL": 10,
            "GRADUATED": 20,
        }

        for _, row in most_recent_df.iterrows():
            subject_id = row["subject_id"]
            current_stage = row.get("current_stage_actual", "")
            session_count = row.get("session", 0)
            water_day_total = row.get("water_day_total", 0)

            # Create threshold alert structure
            subject_threshold_alerts = self._create_threshold_alert_structure(
                session_count, water_day_total, current_stage, row
            )

            # Add stage-specific threshold
            if current_stage in stage_thresholds:
                self._add_stage_threshold(
                    subject_threshold_alerts,
                    subject_id,
                    current_stage,
                    stage_thresholds[current_stage],
                )

            # Set overall threshold alert
            if any(
                alert["alert"] == "T"
                for alert in subject_threshold_alerts["specific_alerts"].values()
            ):
                subject_threshold_alerts["threshold_alert"] = "T"

            threshold_alerts[subject_id] = subject_threshold_alerts

        return threshold_alerts

    def _create_threshold_alert_structure(
        self, session_count, water_day_total, current_stage, row
    ):
        """Create the basic threshold alert structure for a subject"""
        return {
            "threshold_alert": "N",
            "session_count": session_count,
            "water_day_total": water_day_total,
            "stage": current_stage,
            "session_date": row.get("session_date"),
            "specific_alerts": {
                "total_sessions": {
                    "value": session_count,
                    "threshold": 40,
                    "alert": "T" if session_count > 40 else "N",
                    "description": (
                        f"Total sessions: {session_count} > 40"
                        if session_count > 40
                        else ""
                    ),
                },
                "water_day_total": {
                    "value": water_day_total,
                    "threshold": 3.5,
                    "alert": "T" if water_day_total > 3.5 else "N",
                    "description": (
                        f"Water day total: {water_day_total} > 3.5ml"
                        if water_day_total > 3.5
                        else ""
                    ),
                },
            },
        }

    def _add_stage_threshold(
        self, subject_threshold_alerts, subject_id, current_stage, stage_threshold
    ):
        """Add stage-specific threshold alert to subject"""
        stage_sessions_count = 0
        if hasattr(self.app_utils, "get_session_data"):
            all_sessions = self.app_utils.get_session_data()
            stage_sessions_count = len(
                all_sessions[
                    (all_sessions["subject_id"] == subject_id)
                    & (all_sessions["current_stage_actual"] == current_stage)
                ]
            )

        subject_threshold_alerts["specific_alerts"]["stage_sessions"] = {
            "value": stage_sessions_count,
            "threshold": stage_threshold,
            "alert": "T" if stage_sessions_count > stage_threshold else "N",
            "description": (
                f"{current_stage}: {stage_sessions_count} > {stage_threshold}"
                if stage_sessions_count > stage_threshold
                else ""
            ),
            "stage": current_stage,
        }

    def _determine_all_subjects(self, subject_ids, quantile_alerts, threshold_alerts):
        """Determine the complete set of subjects to process"""
        all_subjects = set()

        if subject_ids is not None:
            all_subjects.update(subject_ids)
        else:
            all_subjects.update(quantile_alerts.keys())
            all_subjects.update(threshold_alerts.keys())

            # Include all subjects from session data if no specific IDs requested
            if hasattr(self.app_utils, "get_session_data"):
                df = self.app_utils.get_session_data()
                if df is not None and not df.empty:
                    all_subjects.update(df["subject_id"].unique())

        return all_subjects

    def _handle_off_curriculum_subjects(self, all_subjects, unified_alerts):
        """Handle off-curriculum subjects by setting them as NS"""
        for subject_id in all_subjects:
            if (
                hasattr(self.app_utils, "off_curriculum_subjects")
                and subject_id in self.app_utils.off_curriculum_subjects
            ):
                ns_reason = self.get_not_scored_reason(subject_id)
                unified_alerts[subject_id] = {
                    "alert_category": "NS",
                    "overall_percentile": None,
                    "ns_reason": ns_reason,
                    "threshold": {"threshold_alert": "N", "specific_alerts": {}},
                }

    def _process_quantile_and_threshold_alerts(
        self, quantile_alerts, threshold_alerts, unified_alerts
    ):
        """Process and combine quantile and threshold alerts"""
        # Get off-curriculum subjects for filtering
        off_curriculum_subjects = set()
        if hasattr(self.app_utils, "off_curriculum_subjects"):
            off_curriculum_subjects = set(self.app_utils.off_curriculum_subjects.keys())

        # Process quantile alerts (excluding off-curriculum subjects already handled)
        for subject_id, alerts in quantile_alerts.items():
            if subject_id not in off_curriculum_subjects:
                unified_alerts[subject_id] = {
                    "quantile": alerts,
                    "threshold": threshold_alerts.get(
                        subject_id, {"threshold_alert": "N", "specific_alerts": {}}
                    ),
                }

        # Add subjects that only have threshold alerts
        for subject_id, alerts in threshold_alerts.items():
            if subject_id not in unified_alerts:
                unified_alerts[subject_id] = {
                    "quantile": {"current": {}, "historical": {}},
                    "threshold": alerts,
                }

    def _add_feature_percentiles(self, unified_alerts, subject_ids):
        """Add feature-specific percentiles and categories to unified alerts"""
        if (
            hasattr(self.app_utils, "quantile_analyzer")
            and self.app_utils.quantile_analyzer is not None
        ):
            all_data = self.app_utils.quantile_analyzer.create_comprehensive_dataframe(
                include_history=False
            )

            if not all_data.empty:
                self._process_feature_percentiles(all_data, unified_alerts, subject_ids)

    def _process_feature_percentiles(self, all_data, unified_alerts, subject_ids):
        """Process feature percentiles from comprehensive dataframe"""
        percentile_cols = [
            col for col in all_data.columns if col.endswith("_percentile")
        ]

        # Filter to specified subjects if provided
        if subject_ids is not None:
            all_data = all_data[all_data["subject_id"].isin(subject_ids)]

        # Process each subject
        for subject_id in all_data["subject_id"].unique():
            if subject_id not in unified_alerts:
                continue

            # Get current strata data for this subject
            subject_data = all_data[
                (all_data["subject_id"] == subject_id) & (all_data["is_current"])
            ]

            if subject_data.empty:
                continue

            row = subject_data.iloc[0]
            feature_percentiles, percentile_values = self._extract_feature_percentiles(
                row, percentile_cols
            )

            # Add to unified alerts
            unified_alerts[subject_id]["feature_percentiles"] = feature_percentiles

            # Calculate overall percentile as average of feature percentiles
            if percentile_values:
                calculated_overall = sum(percentile_values) / len(percentile_values)
                unified_alerts[subject_id][
                    "calculated_overall_percentile"
                ] = calculated_overall

            # Add strata information
            if "strata" in row:
                unified_alerts[subject_id]["strata"] = row["strata"]

    def _extract_feature_percentiles(self, row, percentile_cols):
        """Extract feature percentiles from a data row"""
        feature_percentiles = {}
        percentile_values = []

        for col in percentile_cols:
            feature = col.replace("_percentile", "")
            percentile = row[col] if col in row and not pd.isna(row[col]) else None

            if percentile is None:
                continue

            percentile_values.append(percentile)
            category = self.map_percentile_to_category(percentile)

            feature_percentiles[feature] = {
                "percentile": percentile,
                "category": category,
                "description": self.get_category_description(category),
            }

            # Add processed value if available
            processed_col = f"{feature}_processed"
            if processed_col in row and not pd.isna(row[processed_col]):
                feature_percentiles[feature]["processed_value"] = row[processed_col]

        return feature_percentiles, percentile_values

    def _add_overall_percentiles(self, all_subjects, unified_alerts):
        """Calculate and add overall percentiles to unified alerts"""
        overall_percentiles = {}
        try:
            overall_df = self.app_utils.get_session_overall_percentiles(
                list(all_subjects)
            )
            if not overall_df.empty:
                overall_percentiles = dict(
                    zip(
                        overall_df["subject_id"],
                        overall_df["session_overall_percentile"],
                    )
                )
        except Exception as e:
            self.logger.error(
                f"Error calculating session-level overall percentiles: {e}"
            )

        # Add overall percentiles and categories to all subjects
        for subject_id in unified_alerts:
            self._process_subject_overall_percentile(
                subject_id, unified_alerts, overall_percentiles
            )

    def _process_subject_overall_percentile(
        self, subject_id, unified_alerts, overall_percentiles
    ):
        """Process overall percentile for a single subject"""
        # Use calculated percentile if available, otherwise fall back to app_utils
        if "calculated_overall_percentile" in unified_alerts[subject_id]:
            overall_percentile = unified_alerts[subject_id][
                "calculated_overall_percentile"
            ]
            unified_alerts[subject_id].pop("calculated_overall_percentile", None)
        else:
            overall_percentile = overall_percentiles.get(subject_id)

        # Add to unified alerts
        unified_alerts[subject_id]["overall_percentile"] = overall_percentile

        # Calculate alert category from overall percentile
        if overall_percentile is not None and not np.isnan(overall_percentile):
            alert_category = self.map_overall_percentile_to_category(overall_percentile)
        else:
            alert_category = "NS"
            if "ns_reason" not in unified_alerts[subject_id]:
                unified_alerts[subject_id]["ns_reason"] = self.get_not_scored_reason(
                    subject_id
                )

        unified_alerts[subject_id]["alert_category"] = alert_category

    def _handle_subjects_without_alerts(self, all_subjects, unified_alerts):
        """Handle subjects that don't have alerts yet"""
        subjects_without_alerts = all_subjects - set(unified_alerts.keys())
        for subject_id in subjects_without_alerts:
            ns_reason = self.get_not_scored_reason(subject_id)
            unified_alerts[subject_id] = {
                "quantile": {"current": {}, "historical": {}},
                "threshold": {"threshold_alert": "N", "specific_alerts": {}},
                "overall_percentile": None,
                "alert_category": "NS",
                "ns_reason": ns_reason,
            }
