from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from app_utils.simple_logger import get_logger
from app_utils.strata_utils import get_strata_abbreviation

logger = get_logger("ui_utils")


class UIDataManager:
    """
    UI Data Manager for creating optimized data structures for fast component rendering
    """

    def __init__(self):
        """Initialize UI Data Manager"""
        self.features = [
            "finished_trials",
            "ignore_rate",
            "total_trials",
            "foraging_performance",
            "abs(bias_naive)",
        ]

    def map_percentile_to_category(self, percentile: float) -> str:
        """
        Map percentile value to alert category

        Parameters:
            percentile: float
                Percentile value (0-100)

        Returns:
            str: Alert category (SB, B, N, G, SG)
        """
        if pd.isna(percentile):
            return "NS"

        # Use the correct thresholds from the alert service
        if percentile < 6.5:
            return "SB"  # Severely Below: < 6.5%
        elif percentile < 28:
            return "B"  # Below: < 28%
        elif percentile <= 72:
            return "N"  # Normal: 28% - 72%
        elif percentile <= 93.5:
            return "G"  # Good: 72% - 93.5%
        else:
            return "SG"  # Significantly Good: > 93.5%

    def get_strata_abbreviation(self, strata: str) -> str:
        """Get abbreviated strata name for UI display"""
        return get_strata_abbreviation(strata)

    def optimize_session_data_storage(
        self, session_data: pd.DataFrame, cache_manager=None
    ) -> Dict[str, Any]:
        """
        Optimize session-level data storage for efficient lookup and memory usage

        This creates optimized data structures for:
        1. Subject-indexed session data
        2. Strata-indexed reference distributions
        3. Compressed historical data
        4. Wilson confidence intervals for statistical robustness

        Parameters:
            session_data: pd.DataFrame
                Complete session-level data from unified pipeline
            cache_manager: Optional cache manager for data hashing

        Returns:
            Dict[str, Any]: Optimized storage structure with Wilson CI support
        """

        # Handle empty DataFrame case
        if session_data.empty or "subject_id" not in session_data.columns:
            return {
                "subjects": {},
                "strata_reference": {},
                "metadata": {
                    "total_subjects": 0,
                    "total_sessions": 0,
                    "total_strata": 0,
                    "data_hash": "",
                    "wilson_ci_enabled": True,
                    "optimization_timestamp": datetime.now().isoformat(),
                },
            }

        # Create subject-indexed storage for fast subject lookups
        subject_data = {}
        strata_reference = {}

        # Group by subject for efficient subject-based operations
        for subject_id, subject_sessions in session_data.groupby("subject_id"):
            # Sort sessions by date
            subject_sessions = subject_sessions.sort_values("session_date")

            # Store only essential columns to save memory
            essential_columns = [
                "subject_id",
                "session_date",
                "session",
                "strata",
                "session_index",
                "session_overall_percentile",
                "overall_percentile_category",
                "session_overall_rolling_avg",
                "is_current_strata",
                "is_last_session",
                "outlier_weight",
                "is_outlier",
                "PI",
                "trainer",
                "rig",
                "current_stage_actual",
                "curriculum_name",
                "water_day_total",
                "base_weight",
                "target_weight",
                "weight_after",
                "total_trials",
                "finished_trials",
                "ignore_rate",
                "foraging_performance",
                "abs(bias_naive)",
                "finished_rate",
                "total_trials_with_autowater",
                "finished_trials_with_autowater",
                "finished_rate_with_autowater",
                "ignore_rate_with_autowater",
                "autowater_collected",
                "autowater_ignored",
                "water_day_total_last_session",
                "water_after_session_last_session",
            ]

            # Add feature-specific columns
            feature_columns = [
                col
                for col in subject_sessions.columns
                if col.endswith(
                    ("_session_percentile", "_category", "_processed_rolling_avg")
                )
            ]
            essential_columns.extend(feature_columns)

            # Add Wilson confidence interval columns
            ci_columns = [
                col
                for col in subject_sessions.columns
                if col.endswith(("_ci_lower", "_ci_upper"))
            ]
            essential_columns.extend(ci_columns)

            # Filter to available columns and ensure uniqueness
            available_columns = [
                col for col in essential_columns if col in subject_sessions.columns
            ]
            # Remove duplicates while preserving order
            unique_columns = []
            seen = set()
            for col in available_columns:
                if col not in seen:
                    unique_columns.append(col)
                    seen.add(col)

            # Store compressed subject data
            subject_data[subject_id] = {
                "sessions": subject_sessions[unique_columns].to_dict("records"),
                "current_strata": subject_sessions["strata"].iloc[-1],
                "total_sessions": len(subject_sessions),
                "first_session_date": subject_sessions["session_date"].min(),
                "last_session_date": subject_sessions["session_date"].max(),
                "strata_history": subject_sessions[["strata", "session_date"]]
                .drop_duplicates("strata")
                .to_dict("records"),
            }

        # Create strata-indexed reference distributions for percentile calculations
        for strata, strata_sessions in session_data.groupby("strata"):
            processed_features = [
                col
                for col in strata_sessions.columns
                if col.endswith("_processed_rolling_avg")
            ]

            # Create strata reference even if no processed features exist
            reference_distributions = {}
            if processed_features:
                reference_data = strata_sessions[
                    processed_features + ["subject_id"]
                ].dropna()
                reference_distributions = {
                    feature: reference_data[feature].values.tolist()
                    for feature in processed_features
                    if not reference_data[feature].isna().all()
                }

            strata_reference[strata] = {
                "subject_count": len(strata_sessions["subject_id"].unique()),
                "session_count": len(strata_sessions),
                "reference_distributions": reference_distributions,
            }

        # Create optimized storage structure
        data_hash = self._calculate_data_hash(session_data, cache_manager)
        optimized_storage = {
            "subjects": subject_data,
            "strata_reference": strata_reference,
            "metadata": {
                "total_subjects": len(subject_data),
                "total_sessions": len(session_data),
                "total_strata": len(strata_reference),
                "storage_timestamp": pd.Timestamp.now(),
                "data_hash": data_hash,
                "wilson_ci_enabled": True,
            },
        }

        logger.info(
            f"Created optimized storage and UI structures for {len(subject_data)} subjects"
        )

        return optimized_storage

    def _calculate_data_hash(self, df: pd.DataFrame, cache_manager=None) -> str:
        """Calculate a hash for data validation"""
        if cache_manager is not None and hasattr(cache_manager, "calculate_data_hash"):
            return cache_manager.calculate_data_hash(df)

        # Fallback hash calculation
        import hashlib

        data_str = f"{len(df)}_{df['subject_id'].nunique()}_{df['session_date'].max()}"
        return hashlib.md5(data_str.encode()).hexdigest()[:8]

    def create_ui_optimized_structures(
        self, session_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Create UI-optimized data structures for fast rendering

        This creates optimized data structures for:
        1. Subject detail views (time series data)
        2. Table display cache (most recent sessions)
        3. Strata lookup optimization
        4. Wilson confidence intervals for visualization

        Parameters:
            session_data: pd.DataFrame
                Complete session-level data from pipeline

        Returns:
            Dict[str, Any]: UI-optimized structures with Wilson CI support
        """
        # Initialize UI structure
        ui_structures = {
            "time_series_data": {},
            "table_display_cache": [],
            "subject_lookup": {},
            "strata_lookup": {},
        }

        # Handle edge case where session_data is empty
        if session_data.empty:
            return ui_structures

        for subject_id, subject_sessions in session_data.groupby("subject_id"):
            # Sort by date to get proper order
            subject_sessions = subject_sessions.sort_values("session_date")
            latest_session = subject_sessions.iloc[-1]

            ui_structures["subject_lookup"][subject_id] = {
                "latest_session": {
                    "session_date": latest_session["session_date"],
                    "session": latest_session["session"],
                    "strata": latest_session["strata"],
                    "overall_percentile": latest_session.get(
                        "session_overall_percentile"
                    ),
                    "overall_category": latest_session.get(
                        "overall_percentile_category", "NS"
                    ),
                    "PI": latest_session.get("PI", "N/A"),
                    "trainer": latest_session.get("trainer", "N/A"),
                    "rig": latest_session.get("rig", "N/A"),
                },
                "summary": {
                    "total_sessions": len(subject_sessions),
                    "first_session_date": subject_sessions["session_date"].min(),
                    "last_session_date": subject_sessions["session_date"].max(),
                    "unique_strata": subject_sessions["strata"].nunique(),
                    "current_strata": latest_session["strata"],
                },
            }

        for strata, strata_sessions in session_data.groupby("strata"):
            unique_subjects = strata_sessions["subject_id"].nunique()
            total_sessions = len(strata_sessions)

            # Calculate strata performance metrics
            overall_percentiles = strata_sessions["session_overall_percentile"].dropna()

            ui_structures["strata_lookup"][strata] = {
                "subject_count": unique_subjects,
                "session_count": total_sessions,
                "avg_performance": (
                    overall_percentiles.mean() if len(overall_percentiles) > 0 else None
                ),
                "performance_std": (
                    overall_percentiles.std() if len(overall_percentiles) > 0 else None
                ),
                "subjects": strata_sessions["subject_id"].unique().tolist(),
            }

        ui_structures["time_series_data"] = self._create_time_series_data(session_data)

        ui_structures["table_display_cache"] = self._create_table_display_cache(
            session_data
        )

        # Store data hash in UI structures for cache validation
        ui_structures["data_hash"] = self._calculate_data_hash(session_data)

        logger.info(
            f"UI structures created for {len(ui_structures['time_series_data'])} subjects"
        )

        return ui_structures

    def _process_subject_time_series(
        self,
        subject_id: str,
        subject_sessions_data: pd.DataFrame,
        feature_stats: dict,
        overall_stats: dict,
        high_outlier_subjects: list,
    ) -> dict:
        """
        Extract helper method to process individual subject time series data

        This reduces complexity in _create_time_series_data by handling
        the processing logic for a single subject.
        """
        subject_sessions = subject_sessions_data.sort_values("session_date")

        # Extract time series data in compressed format
        time_series = {
            "sessions": subject_sessions["session"].tolist(),
            "dates": subject_sessions["session_date"].dt.strftime("%Y-%m-%d").tolist(),
            "overall_percentiles": subject_sessions["session_overall_percentile"]
            .fillna(-1)
            .tolist(),
            "overall_rolling_avg": subject_sessions["session_overall_rolling_avg"]
            .fillna(-1)
            .tolist(),
            "strata": subject_sessions["strata"].tolist(),
        }

        # Add Wilson confidence intervals for overall percentiles
        self._add_overall_wilson_ci(time_series, subject_sessions, overall_stats)

        # Add outlier detection information
        self._add_outlier_detection_info(
            time_series, subject_sessions, subject_id, high_outlier_subjects
        )

        # Add feature-specific data
        self._add_feature_data_to_time_series(
            time_series, subject_sessions, feature_stats
        )

        return time_series

    def _add_overall_wilson_ci(
        self, time_series: dict, subject_sessions: pd.DataFrame, overall_stats: dict
    ):
        """Add Wilson confidence intervals for overall percentiles"""
        if "session_overall_percentile_ci_lower" in subject_sessions.columns:
            time_series["overall_percentiles_ci_lower"] = (
                subject_sessions["session_overall_percentile_ci_lower"]
                .fillna(-1)
                .tolist()
            )
            time_series["overall_percentiles_ci_upper"] = (
                subject_sessions["session_overall_percentile_ci_upper"]
                .fillna(-1)
                .tolist()
            )
            valid_ci_count = len(
                subject_sessions["session_overall_percentile_ci_lower"].dropna()
            )
            if valid_ci_count > 0:
                overall_stats["ci_sessions"] += valid_ci_count
                overall_stats["subjects_with_data"] += 1

    def _add_outlier_detection_info(
        self,
        time_series: dict,
        subject_sessions: pd.DataFrame,
        subject_id: str,
        high_outlier_subjects: list,
    ):
        """Add outlier detection information for visualization"""
        if "is_outlier" in subject_sessions.columns:
            time_series["is_outlier"] = (
                subject_sessions["is_outlier"].fillna(False).tolist()
            )
            outlier_count = subject_sessions["is_outlier"].sum()
            if outlier_count > len(subject_sessions) * 0.2:
                high_outlier_subjects.append(
                    (subject_id, outlier_count, len(subject_sessions))
                )

    def _add_feature_data_to_time_series(
        self, time_series: dict, subject_sessions: pd.DataFrame, feature_stats: dict
    ):
        """Add RAW feature values for timeseries plotting"""
        for feature in self.features:
            # Store raw feature values for timeseries component to apply its own rolling average
            if feature in subject_sessions.columns:
                time_series[f"{feature}_raw"] = (
                    subject_sessions[feature].fillna(-1).tolist()
                )
                valid_count = len(subject_sessions[feature].dropna())
                if valid_count > 0:
                    feature_stats[feature]["subjects_with_data"] += 1
                    feature_stats[feature]["total_valid_points"] += valid_count

            # Keep percentiles for fallback compatibility
            percentile_col = f"{feature}_session_percentile"
            if percentile_col in subject_sessions.columns:
                time_series[f"{feature}_percentiles"] = (
                    subject_sessions[percentile_col].fillna(-1).tolist()
                )

            # Add Wilson confidence intervals for feature percentiles
            self._add_feature_wilson_ci(
                time_series, subject_sessions, feature, feature_stats
            )

    def _add_feature_wilson_ci(
        self,
        time_series: dict,
        subject_sessions: pd.DataFrame,
        feature: str,
        feature_stats: dict,
    ):
        """Add Wilson confidence intervals for feature percentiles"""
        ci_lower_col = f"{feature}_session_percentile_ci_lower"
        ci_upper_col = f"{feature}_session_percentile_ci_upper"

        if (
            ci_lower_col in subject_sessions.columns
            and ci_upper_col in subject_sessions.columns
        ):
            time_series[f"{feature}_percentile_ci_lower"] = (
                subject_sessions[ci_lower_col].fillna(-1).tolist()
            )
            time_series[f"{feature}_percentile_ci_upper"] = (
                subject_sessions[ci_upper_col].fillna(-1).tolist()
            )
            valid_ci_count = len(subject_sessions[ci_lower_col].dropna())
            feature_stats[feature]["ci_sessions"] += valid_ci_count

    def _create_time_series_data(self, session_data: pd.DataFrame) -> Dict[str, Any]:
        """Create time series data for visualization components with Wilson CIs"""
        time_series_data = {}

        # Counters for aggregate reporting instead of per-subject spam
        total_subjects_processed = 0
        feature_stats = {
            feature: {
                "subjects_with_data": 0,
                "total_valid_points": 0,
                "ci_sessions": 0,
            }
            for feature in self.features
        }
        overall_stats = {
            "subjects_with_data": 0,
            "total_valid_points": 0,
            "ci_sessions": 0,
        }
        high_outlier_subjects = []

        for subject_id, subject_sessions_data in session_data.groupby("subject_id"):
            total_subjects_processed += 1
            time_series_data[subject_id] = self._process_subject_time_series(
                subject_id,
                subject_sessions_data,
                feature_stats,
                overall_stats,
                high_outlier_subjects,
            )

        # Log aggregate summaries
        self._log_time_series_summary(
            total_subjects_processed,
            high_outlier_subjects,
            feature_stats,
            overall_stats,
        )

        return time_series_data

    def _log_time_series_summary(
        self,
        total_subjects_processed: int,
        high_outlier_subjects: list,
        feature_stats: dict,
        overall_stats: dict,
    ):
        """Log consolidated summary of time series data creation"""
        logger.info(f"Time series data created for {total_subjects_processed} subjects")

        # Log consolidated high outlier summary if any found
        if high_outlier_subjects:
            logger.info(
                f"High outlier rate detected for {len(high_outlier_subjects)} subjects"
            )

        # Log feature-level summaries only if significant
        features_with_data = [
            f for f, stats in feature_stats.items() if stats["subjects_with_data"] > 0
        ]
        if features_with_data:
            logger.info(
                f"Features with data: {len(features_with_data)} ({', '.join(features_with_data)})"
            )

        # Report overall percentile summary
        if overall_stats["subjects_with_data"] > 0:
            logger.info(
                f"Overall percentiles: {overall_stats['subjects_with_data']} subjects with Wilson CI data"
            )

    def _calculate_threshold_alerts(
        self, row: pd.Series, subject_sessions: pd.DataFrame
    ) -> tuple:
        """
        Calculate threshold alerts for a subject

        Returns tuple of (total_sessions_alert, stage_sessions_alert, water_day_total_alert, overall_threshold_alert)
        """
        from app_utils.app_analysis.threshold_analyzer import ThresholdAnalyzer

        threshold_config = {
            "session": {"condition": "gt", "value": 40},
            "water_day_total": {"condition": "gt", "value": 3.5},
        }

        # Stage-specific session thresholds
        stage_thresholds = {
            "STAGE_1": 5,
            "STAGE_2": 5,
            "STAGE_3": 6,
            "STAGE_4": 10,
            "STAGE_FINAL": 10,
            "GRADUATED": 20,
        }

        # Combine general thresholds with stage-specific thresholds
        combined_config = threshold_config.copy()
        for stage, threshold in stage_thresholds.items():
            combined_config[f"stage_{stage}_sessions"] = {
                "condition": "gt",
                "value": threshold,
            }

        threshold_analyzer = ThresholdAnalyzer(combined_config)

        # Initialize alert values
        total_sessions_alert = "N"
        stage_sessions_alert = "N"
        water_day_total_alert = "N"
        overall_threshold_alert = "N"

        if not subject_sessions.empty:
            # Check total sessions alert
            total_sessions_result = threshold_analyzer.check_total_sessions(
                subject_sessions
            )
            total_sessions_alert = total_sessions_result["display_format"]
            if total_sessions_result["alert"] == "T":
                overall_threshold_alert = "T"

            # Check stage-specific sessions alert
            current_stage = row.get("current_stage_actual")
            if current_stage and current_stage in stage_thresholds:
                stage_sessions_result = threshold_analyzer.check_stage_sessions(
                    subject_sessions, current_stage
                )
                stage_sessions_alert = stage_sessions_result["display_format"]
                if stage_sessions_result["alert"] == "T":
                    overall_threshold_alert = "T"

            # Check water day total alert
            water_day_total = row.get("water_day_total")
            if not pd.isna(water_day_total):
                water_alert_result = threshold_analyzer.check_water_day_total(
                    water_day_total
                )
                water_day_total_alert = water_alert_result["display_format"]
                if water_alert_result["alert"] == "T":
                    overall_threshold_alert = "T"

        return (
            total_sessions_alert,
            stage_sessions_alert,
            water_day_total_alert,
            overall_threshold_alert,
        )

    def _create_display_row_base(self, row: pd.Series) -> dict:
        """Create base display row with essential metadata"""
        return {
            "subject_id": row["subject_id"],
            "session_date": row["session_date"],
            "session": row["session"],
            "strata": row["strata"],
            "strata_abbr": self.get_strata_abbreviation(row["strata"]),
            "overall_percentile": row.get("session_overall_percentile"),
            "overall_category": row.get("overall_percentile_category", "NS"),
            "percentile_category": row.get("overall_percentile_category", "NS"),
            "combined_alert": row.get("overall_percentile_category", "NS"),
            "session_overall_rolling_avg": row.get("session_overall_rolling_avg"),
            "PI": row.get("PI", "N/A"),
            "trainer": row.get("trainer", "N/A"),
            "rig": row.get("rig", "N/A"),
            "current_stage_actual": row.get("current_stage_actual", "N/A"),
            "curriculum_name": row.get("curriculum_name", "N/A"),
        }

    def _add_essential_metadata_to_display_row(self, display_row: dict, row: pd.Series):
        """Add essential metadata columns to display row"""
        metadata_columns = [
            "water_day_total",
            "base_weight",
            "target_weight",
            "weight_after",
            "total_trials",
            "finished_trials",
            "ignore_rate",
            "foraging_performance",
            "abs(bias_naive)",
            "finished_rate",
            "water_in_session_foraging",
            "water_in_session_manual",
            "water_in_session_total",
            "water_after_session",
            "target_weight_ratio",
            "weight_after_ratio",
            "reward_volume_left_mean",
            "reward_volume_right_mean",
            "reaction_time_median",
            "reaction_time_mean",
            "early_lick_rate",
            "invalid_lick_ratio",
            "double_dipping_rate_finished_trials",
            "double_dipping_rate_finished_reward_trials",
            "double_dipping_rate_finished_noreward_trials",
            "lick_consistency_mean_finished_trials",
            "lick_consistency_mean_finished_reward_trials",
            "lick_consistency_mean_finished_noreward_trials",
            "avg_trial_length_in_seconds",
        ]

        for col in metadata_columns:
            display_row[col] = row.get(col)

    def _add_autowater_columns_to_display_row(self, display_row: dict, row: pd.Series):
        """Add autowater metrics to display row"""
        autowater_columns = [
            "total_trials_with_autowater",
            "finished_trials_with_autowater",
            "finished_rate_with_autowater",
            "ignore_rate_with_autowater",
            "autowater_collected",
            "autowater_ignored",
            "water_day_total_last_session",
            "water_after_session_last_session",
        ]

        for col in autowater_columns:
            display_row[col] = row.get(col)

    def _create_table_display_cache(
        self, session_data: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        """Create table display cache for fast rendering"""
        # Get most recent session for each subject
        most_recent = (
            session_data.sort_values("session_date")
            .groupby("subject_id")
            .last()
            .reset_index()
        )

        table_data = []
        for _, row in most_recent.iterrows():
            subject_id = row["subject_id"]

            # Get all sessions for this subject (needed for threshold calculations)
            subject_sessions = session_data[session_data["subject_id"] == subject_id]

            # Calculate threshold alerts for this subject
            (
                total_sessions_alert,
                stage_sessions_alert,
                water_day_total_alert,
                overall_threshold_alert,
            ) = self._calculate_threshold_alerts(row, subject_sessions)

            # Create base display row
            display_row = self._create_display_row_base(row)

            # Add essential metadata
            self._add_essential_metadata_to_display_row(display_row, row)

            # Add autowater columns
            self._add_autowater_columns_to_display_row(display_row, row)

            # Set computed threshold alert values
            display_row.update(
                {
                    "threshold_alert": overall_threshold_alert,
                    "total_sessions_alert": total_sessions_alert,
                    "stage_sessions_alert": stage_sessions_alert,
                    "water_day_total_alert": water_day_total_alert,
                    "ns_reason": "",
                    "outlier_weight": row.get("outlier_weight", 1.0),
                    "is_outlier": row.get("is_outlier", False),
                }
            )

            # Add feature-specific data
            self._add_feature_data_to_display_row(display_row, row)

            # Add overall percentile CI columns
            self._add_overall_percentile_ci_to_display_row(display_row, row)

            table_data.append(display_row)

        return table_data

    def _add_feature_data_to_display_row(self, display_row: dict, row: pd.Series):
        """Add feature-specific data (both percentiles and rolling averages) to display row"""
        for feature in self.features:
            percentile_col = f"{feature}_session_percentile"
            category_col = f"{feature}_category"
            rolling_avg_col = f"{feature}_processed_rolling_avg"
            ci_lower_col = f"{feature}_session_percentile_ci_lower"
            ci_upper_col = f"{feature}_session_percentile_ci_upper"

            display_row[f"{feature}_session_percentile"] = row.get(percentile_col)
            display_row[f"{feature}_category"] = row.get(category_col, "NS")
            display_row[f"{feature}_processed_rolling_avg"] = row.get(rolling_avg_col)

            # Wilson CI columns (for percentile CIs)
            ci_lower = row.get(ci_lower_col)
            ci_upper = row.get(ci_upper_col)
            display_row[f"{feature}_session_percentile_ci_lower"] = ci_lower
            display_row[f"{feature}_session_percentile_ci_upper"] = ci_upper

            # Calculate and add certainty classification for this feature
            certainty = self._calculate_feature_certainty(
                row, feature, ci_lower, ci_upper, percentile_col
            )
            display_row[f"{feature}_certainty"] = certainty

    def _calculate_feature_certainty(
        self, row: pd.Series, feature: str, ci_lower, ci_upper, percentile_col: str
    ) -> str:
        """Calculate certainty classification for a feature"""
        if (
            ci_lower is not None
            and ci_upper is not None
            and not pd.isna(ci_lower)
            and not pd.isna(ci_upper)
        ):
            ci_width = ci_upper - ci_lower
            percentile_value = row.get(percentile_col)
            if percentile_value is not None and not pd.isna(percentile_value):
                return self._calculate_ci_certainty_moderate(
                    ci_width, percentile_value, feature
                )
            else:
                return "unknown"
        else:
            return "unknown"

    def _add_overall_percentile_ci_to_display_row(
        self, display_row: dict, row: pd.Series
    ):
        """Add overall percentile CI columns to display row"""
        overall_ci_lower_col = "session_overall_percentile_ci_lower"
        overall_ci_upper_col = "session_overall_percentile_ci_upper"
        overall_ci_lower = row.get(overall_ci_lower_col)
        overall_ci_upper = row.get(overall_ci_upper_col)

        display_row[overall_ci_lower_col] = overall_ci_lower
        display_row[overall_ci_upper_col] = overall_ci_upper

        # Calculate overall percentile certainty
        if (
            overall_ci_lower is not None
            and overall_ci_upper is not None
            and not pd.isna(overall_ci_lower)
            and not pd.isna(overall_ci_upper)
        ):
            overall_ci_width = overall_ci_upper - overall_ci_lower
            overall_percentile = row.get("session_overall_percentile")
            if overall_percentile is not None and not pd.isna(overall_percentile):
                overall_certainty = self._calculate_ci_certainty_moderate(
                    overall_ci_width, overall_percentile, "overall"
                )
                display_row["session_overall_percentile_certainty"] = overall_certainty
            else:
                display_row["session_overall_percentile_certainty"] = "unknown"
        else:
            display_row["session_overall_percentile_certainty"] = "unknown"

    def get_subject_display_data(
        self, subject_id: str, ui_structures: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get optimized subject data for UI display components

        Parameters:
            subject_id: str
                Subject ID to get display data for
            ui_structures: Dict[str, Any]
                Pre-computed UI structures

        Returns:
            Dict[str, Any]: Subject display data optimized for UI rendering
        """
        return ui_structures.get("subject_lookup", {}).get(subject_id, {})

    def get_table_display_data(
        self, ui_structures: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get optimized table display data for fast rendering

        Parameters:
            ui_structures: Dict[str, Any]
                Pre-computed UI structures

        Returns:
            List[Dict[str, Any]]: Table data optimized for UI rendering
        """
        return ui_structures.get("table_display_cache", [])

    def get_time_series_data(
        self, subject_id: str, ui_structures: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get optimized time series data for visualization components

        Parameters:
            subject_id: str
                Subject ID to get time series data for
            ui_structures: Dict[str, Any]
                Pre-computed UI structures

        Returns:
            Dict[str, Any]: Time series data optimized for UI rendering
        """
        return ui_structures.get("time_series_data", {}).get(subject_id, {})

    def _calculate_ci_certainty_moderate(
        self, ci_width: float, target_value: float, feature_name: str = None
    ) -> str:
        """
        Calculate CI certainty using 3-tier system based on CI width relative to point estimate

        Parameters:
            ci_width: float
                Width of the confidence interval
            target_value: float
                Point estimate (rolling average value) for relative threshold calculation
            feature_name: str
                Optional feature name (currently unused, kept for compatibility)

        Returns:
            str: 'certain', 'intermediate', or 'uncertain' based on CI width relative to point estimate

        Criteria:
            - certain: CI width ≤ 30% of point estimate
            - intermediate: 30% < CI width < 60% of point estimate
            - uncertain: CI width ≥ 60% of point estimate
        """
        # Handle edge cases
        if pd.isna(ci_width) or pd.isna(target_value):
            return "intermediate"

        # Avoid division by zero - if target_value is very small, use absolute threshold
        if abs(target_value) < 1e-6:
            # For very small target values, use absolute thresholds
            if ci_width <= 0.01:  # Very narrow CI
                return "certain"
            elif ci_width >= 0.05:  # Very wide CI
                return "uncertain"
            else:
                return "intermediate"

        # Calculate relative CI width as percentage of point estimate
        relative_ci_width = ci_width / abs(target_value)

        # Apply 3-tier thresholds
        if relative_ci_width <= 0.30:  # CI width ≤ 30% of point estimate
            return "certain"
        elif relative_ci_width >= 0.60:  # CI width ≥ 60% of point estimate
            return "uncertain"
        else:  # 30% < CI width < 60% of point estimate
            return "intermediate"


def get_optimized_table_data(app_utils, use_cache: bool = True) -> pd.DataFrame:
    """
    Get optimized table data with intelligent cache fallback strategy

    This function implements the complex fallback chain for getting table data:
    1. UI-optimized table display data (fastest path)
    2. Cached session-level data with most recent session selection
    3. Pipeline re-run as last resort

    Parameters:
        app_utils: AppUtils instance
        use_cache: bool, whether to use cached data

    Returns:
        pd.DataFrame: Recent sessions data for table display
    """
    logger.info("Getting optimized table data with intelligent cache fallback...")

    # First try to use UI-optimized table display data (fastest path)
    table_data = app_utils.get_table_display_data(use_cache=use_cache)
    if table_data:
        logger.info(f"Loaded {len(table_data)} subjects from UI cache")
        return pd.DataFrame(table_data)

    # Second option: Use cached session-level data
    elif (
        hasattr(app_utils, "_cache")
        and app_utils._cache.get("session_level_data") is not None
    ):
        logger.info("Selected most recent session for subjects")
        return app_utils.get_most_recent_subject_sessions(use_cache=use_cache)

    else:
        # Final fallback - need to run pipeline
        logger.info("Processing data pipeline for table data...")
        # Run pipeline with fresh data processing
        app_utils.process_data_pipeline(use_cache=False)
        return app_utils.get_most_recent_subject_sessions(use_cache=use_cache)


def process_unified_alerts_integration(
    recent_sessions: pd.DataFrame,
    app_utils,
    threshold_config: dict = None,
    stage_thresholds: dict = None,
) -> pd.DataFrame:
    """
    Integrate unified alerts with session data using business logic

    This function handles:
    1. Alert service initialization
    2. Unified alerts retrieval
    3. Alert column initialization
    4. Threshold alerts processing
    5. Alert data merging and combining

    Parameters:
        recent_sessions: pd.DataFrame - Session data to integrate alerts with
        app_utils: AppUtils instance
        threshold_config: dict - Threshold configuration for alerts
        stage_thresholds: dict - Stage-specific threshold configuration

    Returns:
        pd.DataFrame: Session data with integrated alerts
    """
    logger.info("Processing unified alerts integration...")

    # Initialize output dataframe with basic alert columns
    output_df = recent_sessions.copy()
    output_df = _initialize_alert_columns(output_df)

    try:
        _ensure_pipeline_and_service_ready(app_utils)

        # Step 3: Get all subject IDs
        subject_ids = recent_sessions["subject_id"].unique().tolist()

        # Step 4: Get unified alerts for these subjects
        unified_alerts = app_utils.get_unified_alerts(subject_ids)
        logger.info(f"Got unified alerts for {len(unified_alerts)} subjects")

        # Step 5: Apply alerts from unified_alerts
        output_df = _apply_unified_alerts_to_output(output_df, unified_alerts)
        logger.info(f"Applied alerts to {len(output_df)} subjects")

    except Exception as e:
        logger.warning(f"Alert processing failed: {str(e)}")
        logger.info("Continuing with default alert values...")
        output_df = _apply_default_alert_values(output_df)

    logger.info(
        f"Pipeline complete: {len(output_df.columns)} columns processed for {len(output_df)} subjects"
    )
    return output_df


def format_strata_abbreviations(
    df: pd.DataFrame, strata_column: str = "strata", abbr_column: str = "strata_abbr"
) -> pd.DataFrame:
    """
    Add abbreviated strata column to dataframe using the centralized function

    Parameters:
        df (pd.DataFrame): Input dataframe containing strata information
        strata_column (str): Name of the column containing full strata names
        abbr_column (str): Name of the column to store abbreviated strata

    Returns:
        pd.DataFrame: Output dataframe with abbreviated strata column added
    """
    # Apply abbreviations to strata names if not already present or if missing strata column
    output_df = df.copy()

    if strata_column not in output_df.columns:
        logger.warning(f"Strata column '{strata_column}' not found in dataframe")
        output_df[abbr_column] = ""
        return output_df

    if abbr_column not in output_df.columns or output_df[abbr_column].isna().all():
        output_df[abbr_column] = output_df[strata_column].apply(get_strata_abbreviation)
        logger.info("Strata abbreviations applied")
    else:
        logger.info("Strata abbreviations already present, skipping")

    return output_df


def create_empty_dataframe_structure() -> pd.DataFrame:
    """
    Create empty dataframe with required columns to avoid breaking UI

    Returns:
        pd.DataFrame: Empty dataframe with essential columns
    """
    return pd.DataFrame(
        columns=[
            "subject_id",
            "combined_alert",
            "percentile_category",
            "overall_percentile",
            "session_date",
            "session",
        ]
    )


def _initialize_alert_columns(output_df: pd.DataFrame) -> pd.DataFrame:
    """Initialize alert columns with default values"""
    for col in [
        "percentile_category",
        "threshold_alert",
        "combined_alert",
        "ns_reason",
        "strata_abbr",
        "total_sessions_alert",
        "stage_sessions_alert",
        "water_day_total_alert",
    ]:
        if col not in output_df.columns:
            default_val = (
                "NS"
                if col in ["percentile_category", "combined_alert"]
                else ("N" if col.endswith("_alert") else "")
            )
            output_df[col] = default_val
    return output_df


def _ensure_pipeline_and_service_ready(app_utils) -> bool:
    """Ensure pipeline has been run and alert service is available"""
    # Step 1: Ensure pipeline has been run and analyzers are available
    if (
        not hasattr(app_utils, "reference_processor")
        or app_utils.reference_processor is None
    ):
        logger.info(
            "Reference processor not available, initializing data pipeline first..."
        )
        raw_data = app_utils.get_session_data(use_cache=True)
        app_utils.process_data_pipeline(raw_data.head(100), use_cache=False)

    # Step 2: Initialize alert service if needed
    if app_utils.alert_coordinator.alert_service is None:
        app_utils.initialize_alert_service()

    return True


def _apply_unified_alerts_to_output(
    output_df: pd.DataFrame, unified_alerts: dict
) -> pd.DataFrame:
    """Apply unified alerts to output dataframe"""
    for subject_id, alerts in unified_alerts.items():
        mask = output_df["subject_id"] == subject_id
        if not mask.any():
            continue

        # Add alert category
        alert_category = alerts.get("alert_category", "NS")
        output_df.loc[mask, "percentile_category"] = alert_category

        # Add NS reason if applicable
        if alert_category == "NS" and "ns_reason" in alerts:
            output_df.loc[mask, "ns_reason"] = alerts["ns_reason"]

        # Apply threshold alerts from unified alerts structure
        threshold_data = alerts.get("threshold", {})
        overall_threshold_alert = threshold_data.get("threshold_alert", "N")

        if overall_threshold_alert == "T":
            output_df.loc[mask, "threshold_alert"] = "T"

        # Combine percentile and threshold alerts for display
        current_threshold_alert = (
            output_df.loc[mask, "threshold_alert"].iloc[0] if mask.any() else "N"
        )

        if current_threshold_alert == "T":
            if alert_category != "NS":
                output_df.loc[mask, "combined_alert"] = f"{alert_category}, T"
            else:
                output_df.loc[mask, "combined_alert"] = "T"
        else:
            output_df.loc[mask, "combined_alert"] = alert_category

    return output_df


def _apply_default_alert_values(output_df: pd.DataFrame) -> pd.DataFrame:
    """Apply default alert values when alert processing fails"""
    for subject_id in output_df["subject_id"].unique():
        mask = output_df["subject_id"] == subject_id
        output_df.loc[mask, "percentile_category"] = "NS"
        output_df.loc[mask, "combined_alert"] = "NS"
        output_df.loc[mask, "ns_reason"] = "Alert service unavailable"
    return output_df
