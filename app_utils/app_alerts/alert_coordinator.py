from typing import Any, Dict, Optional

import pandas as pd

from .alert_service import AlertService


class AlertCoordinator:
    """
    Alert service coordination and initialization class

    This class handles alert service initialization, coordination,
    and caching for the AIND Dashboard.
    """

    def __init__(self, cache_manager=None, pipeline_manager=None):
        """
        Initialize the AlertCoordinator

        Parameters:
            cache_manager: CacheManager instance for alert caching
            pipeline_manager: DataPipelineManager instance for data access
        """
        self.cache_manager = cache_manager
        self.pipeline_manager = pipeline_manager
        self.alert_service = None

    def initialize_alert_service(
        self, app_utils, config: Optional[Dict[str, Any]] = None
    ) -> AlertService:
        """
        Initialize alert service for monitoring and reporting issues

        Parameters:
            app_utils: AppUtils instance that provides data access
            config (Optional[Dict[str, Any]]): Configuration for alert service

        Returns:
            AlertService: Initialized alert service
        """
        # Create alert service with access to the AppUtils instance
        self.alert_service = AlertService(app_utils=app_utils, config=config)

        # Force reset caches for a clean start
        if hasattr(self.alert_service, "force_reset"):
            self.alert_service.force_reset()

        return self.alert_service

    def get_quantile_alerts(self, subject_ids=None):
        """
        Get quantile alerts for given subjects with proper delegation

        Parameters:
            subject_ids (List[str], optional): List of subject IDs to get alerts for

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping subject IDs to their quantile alerts
        """
        if self.alert_service is None:
            raise ValueError(
                "Alert service not initialized. Call initialize_alert_service() first."
            )

        return self.alert_service.get_quantile_alerts(subject_ids)

    def get_unified_alerts(self, subject_ids=None, use_cache=True):
        """
        Get unified alerts with caching support

        Parameters:
            subject_ids (List[str], optional): List of subject IDs to get alerts for
            use_cache (bool): Whether to use cached alerts if available

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping subject IDs to their unified alerts
        """
        # Check if alert service is initialized first
        if self.alert_service is None:
            raise ValueError(
                "Alert service not initialized. Call initialize_alert_service() first."
            )

        # Return cached alerts if available and not requesting specific subjects
        if (
            use_cache
            and subject_ids is None
            and self.cache_manager
            and self.cache_manager.has("unified_alerts")
        ):
            print("Using cached unified alerts")
            return self.cache_manager.get("unified_alerts")

        # Get alerts from alert service
        alerts = self.alert_service.get_unified_alerts(subject_ids)

        # Cache results if getting alerts for all subjects
        if subject_ids is None and self.cache_manager:
            self.cache_manager.set("unified_alerts", alerts)

        return alerts

    def clear_alert_cache(self):
        """
        Clear cached alert data to force refresh
        """
        if self.cache_manager:
            # Clear unified alerts cache
            if self.cache_manager.has("unified_alerts"):
                print("Clearing unified alerts cache")
                pass

        # Clear alert service internal caches if available
        if self.alert_service and hasattr(self.alert_service, "_quantile_alerts"):
            self.alert_service._quantile_alerts = {}

    def get_alert_summary_stats(self, subject_ids=None) -> Dict[str, Any]:
        """
        Get summary statistics for alerts across all subjects

        Parameters:
            subject_ids (List[str], optional): List of subject IDs to analyze

        Returns:
            Dict[str, Any]: Alert summary statistics
        """
        if self.alert_service is None:
            return {
                "error": "Alert service not initialized",
                "total_subjects": 0,
                "category_counts": {},
            }

        try:
            # Get unified alerts for analysis
            alerts = self.get_unified_alerts(subject_ids=subject_ids, use_cache=True)

            # Calculate summary statistics
            total_subjects = len(alerts)
            category_counts = {}

            for subject_id, alert_data in alerts.items():
                category = alert_data.get("alert_category", "Unknown")
                category_counts[category] = category_counts.get(category, 0) + 1

            # Calculate percentages
            category_percentages = {}
            if total_subjects > 0:
                for category, count in category_counts.items():
                    category_percentages[category] = (count / total_subjects) * 100

            return {
                "total_subjects": total_subjects,
                "category_counts": category_counts,
                "category_percentages": category_percentages,
                "categories_found": list(category_counts.keys()),
            }

        except Exception as e:
            return {
                "error": f"Error calculating alert summary: {str(e)}",
                "total_subjects": 0,
                "category_counts": {},
            }

    def validate_alert_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate alert service configuration

        Parameters:
            config (Dict[str, Any]): Alert configuration to validate

        Returns:
            Dict[str, Any]: Validation results with any issues found
        """
        validation_result = {"valid": True, "warnings": [], "errors": []}

        # Check percentile categories if provided
        if "percentile_categories" in config:
            categories = config["percentile_categories"]

            # Expected category keys
            expected_keys = ["SB", "B", "N", "G", "SG"]

            for key in expected_keys:
                if key not in categories:
                    validation_result["errors"].append(
                        f"Missing category threshold: {key}"
                    )
                    validation_result["valid"] = False
                elif not isinstance(categories[key], (int, float)):
                    validation_result["errors"].append(
                        f"Invalid threshold type for {key}: must be numeric"
                    )
                    validation_result["valid"] = False

            # Check threshold ordering
            if validation_result["valid"]:
                thresholds = [categories[key] for key in expected_keys]
                if thresholds != sorted(thresholds):
                    validation_result["warnings"].append(
                        "Category thresholds may not be in expected order"
                    )

        # Check feature configuration
        if "feature_config" in config:
            feature_config = config["feature_config"]
            if not isinstance(feature_config, dict):
                validation_result["errors"].append(
                    "feature_config must be a dictionary"
                )
                validation_result["valid"] = False

        return validation_result

    def filter_by_alert_category(
        self, df: pd.DataFrame, alert_category: str
    ) -> pd.DataFrame:
        """
        Apply alert category filtering

        Parameters:
            df (pd.DataFrame): DataFrame to filter
            alert_category (str): Alert category to filter by ('all', 'T', 'NS', 'B', 'G', 'SB', 'SG')

        Returns:
            pd.DataFrame: Filtered DataFrame with subjects matching the alert category
        """
        if df.empty or alert_category == "all":
            return df

        # Ensure alert service is initialized
        if self.alert_service is None:
            raise ValueError(
                "Alert service not initialized. Call initialize_alert_service() first."
            )

        print(f" Applying alert category filter: {alert_category}")

        if alert_category == "T":
            # Use AlertService for complex threshold alert filtering
            filtered_df = self.alert_service.filter_by_threshold_alerts(df)
        else:
            # Use AlertService for category mask generation with validation
            try:
                mask = self.alert_service.get_alert_category_mask(df, alert_category)
                before_count = len(df)
                filtered_df = df[mask]
                after_count = len(filtered_df)

                print(
                    f"Alert category '{alert_category}' filter applied: {before_count} → {after_count} subjects"
                )

                # Additional validation for category filtering
                if alert_category in ["NS", "B", "G", "SB", "SG"]:
                    # Verify the filtering worked correctly
                    percentile_col = (
                        "overall_percentile_category"
                        if "overall_percentile_category" in filtered_df.columns
                        else "percentile_category"
                    )
                    if percentile_col in filtered_df.columns and not filtered_df.empty:
                        actual_categories = filtered_df[percentile_col].unique()
                        if len(actual_categories) > 1 or (
                            len(actual_categories) == 1
                            and actual_categories[0] != alert_category
                        ):
                            print(
                                f" WARNING: Filter validation failed. Expected '{alert_category}', found: {actual_categories}"
                            )

            except Exception as e:
                print(
                    f" Error applying alert category filter '{alert_category}': {str(e)}"
                )
                # Return original dataframe on error to avoid breaking the UI
                filtered_df = df

        return filtered_df

    def aggregate_alert_categories(self, df: pd.DataFrame) -> Dict[str, int]:
        """
        Count subjects by alert category for summary statistics

        Parameters:
            df (pd.DataFrame): DataFrame to aggregate alert categories for

        Returns:
            Dict[str, int]: Dictionary mapping alert categories to subject counts
        """
        if df.empty:
            return {}

        # Ensure alert service is initialized
        if self.alert_service is None:
            print(" Alert service not initialized, returning basic aggregation")
            return self._fallback_aggregation(df)

        try:
            aggregation_results = self._count_standard_categories(df)
            self._count_threshold_alerts(df, aggregation_results)
            self._validate_and_adjust_counts(df, aggregation_results)

            return aggregation_results

        except Exception as e:
            print(f"Error in alert category aggregation: {str(e)}")
            return self._fallback_aggregation(df)

    def _fallback_aggregation(self, df: pd.DataFrame) -> Dict[str, int]:
        """Fallback aggregation method when alert service is not available"""
        percentile_col = (
            "overall_percentile_category"
            if "overall_percentile_category" in df.columns
            else "percentile_category"
        )
        if percentile_col in df.columns:
            return df[percentile_col].value_counts().to_dict()
        return {}

    def _count_standard_categories(self, df: pd.DataFrame) -> Dict[str, int]:
        """Count subjects in each standard percentile category"""
        aggregation_results = {}
        standard_categories = ["NS", "SB", "B", "N", "G", "SG"]

        for category in standard_categories:
            try:
                mask = self.alert_service.get_alert_category_mask(df, category)
                count = mask.sum() if hasattr(mask, "sum") else 0
                if count > 0:
                    aggregation_results[category] = count
            except Exception as e:
                print(f"Error counting category '{category}': {str(e)}")
                aggregation_results[category] = 0

        return aggregation_results

    def _count_threshold_alerts(
        self, df: pd.DataFrame, aggregation_results: Dict[str, int]
    ):
        """Count threshold alerts and add to aggregation results"""
        try:
            threshold_mask = self.alert_service.get_alert_category_mask(df, "T")
            threshold_count = (
                threshold_mask.sum() if hasattr(threshold_mask, "sum") else 0
            )
            if threshold_count > 0:
                aggregation_results["T"] = threshold_count
        except Exception as e:
            print(f"Error counting threshold alerts: {str(e)}")
            aggregation_results["T"] = 0

    def _validate_and_adjust_counts(
        self, df: pd.DataFrame, aggregation_results: Dict[str, int]
    ):
        """Validate aggregation results and adjust for any missing subjects"""
        total_aggregated = sum(aggregation_results.values())
        actual_total = len(df)

        print(f"Alert category aggregation: {aggregation_results}")
        print(f"Total subjects: {actual_total}, Aggregated: {total_aggregated}")

        # Add any missing subjects to 'Unknown' category if needed
        if total_aggregated < actual_total:
            missing_count = actual_total - total_aggregated
            aggregation_results["Unknown"] = missing_count
            print(f"Added {missing_count} subjects to 'Unknown' category")
