"""
Subject percentile timeseries visualization component for AIND Dashboard

This module creates interactive timeseries plots showing percentile progression
over time with confidence intervals using Wilson CI methodology.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from app_utils.simple_logger import get_logger
from app_utils.strata_utils import get_strata_abbreviation

logger = get_logger("subject_percentile_timeseries")


class AppSubjectPercentileTimeseries:
    def __init__(self):
        """Initialize the percentile timeseries component"""
        # Define features to plot with their optimization preferences
        self.features_config = {
            "finished_trials": False,  # Higher is better
            "ignore_rate": True,  # Lower is better
            "total_trials": False,  # Higher is better
            "foraging_performance": False,  # Higher is better
            "abs(bias_naive)": True,  # Lower is better
        }

        # Color scheme for features
        self.feature_colors = {
            "finished_trials": "#1f77b4",  # Blue
            "ignore_rate": "#ff7f0e",  # Orange
            "total_trials": "#2ca02c",  # Green
            "foraging_performance": "#d62728",  # Red
            "abs(bias_naive)": "#9467bd",  # Purple
        }

    def build(self):
        """Build the complete percentile timeseries component"""
        return html.Div(
            [
                # Feature selection controls
                html.Div(
                    [
                        html.Label(
                            "Feature Percentiles:",
                            className="control-label mb-1",
                            style={"fontSize": "14px", "fontWeight": "600"},
                        ),
                        dcc.Dropdown(
                            id="percentile-timeseries-feature-dropdown",
                            options=self._get_feature_options(),
                            value=["all"],  # Default to all features
                            multi=True,
                            className="percentile-timeseries-feature-dropdown",
                        ),
                        # Add confidence interval toggle
                        html.Div(
                            [
                                dcc.Checklist(
                                    id="percentile-ci-toggle",
                                    options=[
                                        {
                                            "label": " Show 95% Confidence Intervals",
                                            "value": "show_ci",
                                        }
                                    ],
                                    value=["show_ci"],  # Default to showing CI
                                    className="ci-toggle-checklist",
                                    style={"marginTop": "5px", "fontSize": "12px"},
                                )
                            ],
                            className="ci-controls",
                        ),
                    ],
                    className="percentile-timeseries-controls mb-2",
                ),
                # Main percentile timeseries plot
                dcc.Graph(
                    id="percentile-timeseries-plot",
                    figure=self._create_empty_figure(),
                    config={"displayModeBar": False, "responsive": True},
                    className="percentile-timeseries-graph",
                    style={"height": "550px"},
                ),
            ],
            className="subject-percentile-timeseries-component",
        )

    def _get_feature_options(self):
        """Get dropdown options for feature selection"""
        options = [{"label": "All Features", "value": "all"}]

        # Add individual features
        for feature in self.features_config.keys():
            label = (
                feature.replace("_", " ").replace("abs(", "|").replace(")", "|").title()
            )
            options.append({"label": label, "value": feature})

        # Add overall percentile as a selectable option
        options.append({"label": "Overall Percentile", "value": "overall_percentile"})

        return options

    def _create_empty_figure(self):
        """Create empty plot with proper styling"""
        fig = go.Figure()

        fig.update_layout(
            title=None,
            xaxis_title="Session Number",
            yaxis_title="Feature Percentiles",
            template="plotly_white",
            margin=dict(
                l=40,
                r=20,
                t=40,
                b=60,
            ),
            height=550,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
            hovermode="x unified",
            yaxis=dict(
                range=[0, 100],
                showgrid=True,
                gridwidth=1,
                gridcolor="rgba(211,211,211,0.3)",
                zeroline=False,
            ),
        )

        # Add placeholder text
        fig.add_annotation(
            text="Select a subject to view percentile data",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14, color="gray"),
        )

        return fig

    def create_plot(
        self,
        subject_data,
        selected_features,
        highlighted_session=None,
        show_confidence_intervals=True,
    ):
        """
        Create the percentile timeseries plot using Wilson CI methodology

        Parameters:
            subject_data: dict - Time series data from app_utils
            selected_features: list - Features to plot
            highlighted_session: int - Session to highlight
            show_confidence_intervals: bool - Whether to show confidence interval bands
        """
        logger.info(
            f"Creating percentile timeseries plot for subject with data keys: {list(subject_data.keys()) if subject_data else 'None'}"
        )

        # Validate input data
        if not self._validate_input_data(subject_data):
            return self._create_empty_figure()

        fig = go.Figure()
        sessions = subject_data["sessions"]

        # Prepare plot data
        features_to_plot, show_overall_percentile = self._prepare_features_to_plot(
            selected_features
        )
        strata_sessions_map = self._create_strata_mapping(subject_data)

        # Plot individual features
        self._add_feature_traces(
            fig,
            subject_data,
            features_to_plot,
            sessions,
            strata_sessions_map,
            show_confidence_intervals,
        )

        # Add overall percentile if selected
        if show_overall_percentile:
            self._add_overall_percentile_trace(
                fig,
                subject_data,
                sessions,
                strata_sessions_map,
                show_confidence_intervals,
                features_to_plot,
            )

        # Configure plot layout and enhancements
        self._configure_plot_layout(fig)
        self._add_plot_enhancements(fig, subject_data, sessions, highlighted_session)

        return fig

    def _validate_input_data(self, subject_data):
        """Validate input data for plotting"""
        return subject_data and "sessions" in subject_data and subject_data["sessions"]

    def _prepare_features_to_plot(self, selected_features):
        """Determine which features to plot based on selection"""
        features_to_plot = []
        show_overall_percentile = False

        if "all" in selected_features:
            features_to_plot = list(self.features_config.keys())
            show_overall_percentile = True
        else:
            for feature in selected_features:
                if feature in self.features_config:
                    features_to_plot.append(feature)
                elif feature == "overall_percentile":
                    show_overall_percentile = True

            # If no valid features selected, default to all
            if not features_to_plot and not show_overall_percentile:
                features_to_plot = list(self.features_config.keys())
                show_overall_percentile = True

        logger.info(f"Features to plot (percentiles): {features_to_plot}")
        logger.info(f"Show overall percentile: {show_overall_percentile}")

        return features_to_plot, show_overall_percentile

    def _create_strata_mapping(self, subject_data):
        """Create strata abbreviation mapping for hover info"""
        sessions = subject_data["sessions"]
        strata_data = subject_data.get("strata", [])
        strata_sessions_map = {}

        if strata_data and len(strata_data) == len(sessions):
            for session, strata in zip(sessions, strata_data):
                strata_sessions_map[session] = self._get_strata_abbreviation(strata)

        return strata_sessions_map

    def _add_feature_traces(
        self,
        fig,
        subject_data,
        features_to_plot,
        sessions,
        strata_sessions_map,
        show_confidence_intervals,
    ):
        """Add traces for individual features with confidence intervals"""
        for i, feature in enumerate(features_to_plot):
            percentile_key = f"{feature}_percentiles"
            if percentile_key not in subject_data:
                logger.info(f"No percentile data found for {feature}, skipping")
                continue

            # Get and validate data
            valid_data = self._get_valid_percentile_data(
                subject_data, feature, sessions, show_confidence_intervals
            )

            if not valid_data or len(valid_data["sessions"]) < 2:
                logger.info(f"Insufficient valid percentile data for {feature}")
                continue

            # Add confidence interval bands if available
            if valid_data["has_ci"]:
                self._add_confidence_intervals(fig, feature, valid_data)

            # Add main feature trace
            self._add_feature_trace(
                fig, feature, valid_data, strata_sessions_map, i == 0
            )

    def _get_valid_percentile_data(
        self, subject_data, feature, sessions, show_confidence_intervals
    ):
        """Extract and validate percentile data for a feature"""
        percentile_key = f"{feature}_percentiles"
        ci_lower_key = f"{feature}_percentile_ci_lower"
        ci_upper_key = f"{feature}_percentile_ci_upper"

        percentile_data = subject_data[percentile_key]
        ci_lower_data = subject_data.get(ci_lower_key, [])
        ci_upper_data = subject_data.get(ci_upper_key, [])

        has_ci_data = (
            len(ci_lower_data) == len(percentile_data)
            and len(ci_upper_data) == len(percentile_data)
            and show_confidence_intervals
        )

        # Filter out invalid values
        valid_sessions, valid_percentiles, valid_ci_lower, valid_ci_upper = (
            [],
            [],
            [],
            [],
        )

        for j, (session, percentile) in enumerate(zip(sessions, percentile_data)):
            if percentile is not None and not pd.isna(percentile) and percentile != -1:
                valid_sessions.append(session)
                valid_percentiles.append(percentile)

                if has_ci_data and j < len(ci_lower_data) and j < len(ci_upper_data):
                    ci_lower = ci_lower_data[j]
                    ci_upper = ci_upper_data[j]

                    if (
                        ci_lower is not None
                        and not pd.isna(ci_lower)
                        and ci_lower != -1
                        and ci_upper is not None
                        and not pd.isna(ci_upper)
                        and ci_upper != -1
                    ):
                        valid_ci_lower.append(ci_lower)
                        valid_ci_upper.append(ci_upper)
                    else:
                        valid_ci_lower.append(None)
                        valid_ci_upper.append(None)

        return {
            "sessions": valid_sessions,
            "percentiles": valid_percentiles,
            "ci_lower": valid_ci_lower,
            "ci_upper": valid_ci_upper,
            "has_ci": has_ci_data and len(valid_ci_lower) == len(valid_sessions),
        }

    def _add_confidence_intervals(self, fig, feature, valid_data):
        """Add confidence interval bands for a feature"""
        # Filter CI data to match valid sessions
        valid_ci_lower = [ci for ci in valid_data["ci_lower"] if ci is not None]
        valid_ci_upper = [ci for ci in valid_data["ci_upper"] if ci is not None]
        valid_sessions_ci = [
            session
            for session, ci_lower, ci_upper in zip(
                valid_data["sessions"], valid_data["ci_lower"], valid_data["ci_upper"]
            )
            if ci_lower is not None and ci_upper is not None
        ]

        if not valid_ci_lower or not valid_sessions_ci:
            return

        feature_color = self.feature_colors.get(feature, "#000000")

        # Add upper bound (invisible line)
        fig.add_trace(
            go.Scatter(
                x=valid_sessions_ci,
                y=valid_ci_upper,
                fill=None,
                mode="lines",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                hoverinfo="skip",
                name=f"{feature}_ci_upper",
            )
        )

        # Add lower bound with fill
        fig.add_trace(
            go.Scatter(
                x=valid_sessions_ci,
                y=valid_ci_lower,
                fill="tonexty",
                mode="lines",
                line=dict(color="rgba(0,0,0,0)"),
                fillcolor=f"rgba({self._hex_to_rgb(feature_color)}, 0.2)",
                showlegend=False,
                hoverinfo="skip",
                name=f"{feature}_ci_band",
            )
        )

        logger.info(f"Added CI bands for {feature}: {len(valid_sessions_ci)} sessions")

    def _add_feature_trace(
        self, fig, feature, valid_data, strata_sessions_map, is_first_trace
    ):
        """Add main feature trace to the plot"""
        feature_color = self.feature_colors.get(feature, "#000000")

        # Prepare hover data and template
        hover_template, custom_data = self._prepare_hover_data(
            feature, valid_data, strata_sessions_map, is_first_trace
        )

        # Create trace for feature percentiles
        fig.add_trace(
            go.Scatter(
                x=valid_data["sessions"],
                y=valid_data["percentiles"],
                mode="lines",
                name=feature.replace("_", " ")
                .replace("abs(", "|")
                .replace(")", "|")
                .title(),
                line=dict(color=feature_color, width=2, shape="spline", smoothing=1.0),
                hovertemplate=hover_template,
                customdata=custom_data,
            )
        )

    def _prepare_hover_data(
        self, feature, valid_data, strata_sessions_map, is_first_trace
    ):
        """Prepare hover template and custom data for a feature trace"""
        if is_first_trace:
            strata_hover_info = [
                strata_sessions_map.get(session, "Unknown")
                for session in valid_data["sessions"]
            ]

            if valid_data["has_ci"]:
                hover_template = (
                    "<b>Strata: %{customdata[1]}</b><br><br>"
                    + f"<b>{feature.replace('_', ' ').title()}</b><br>"
                    + "Percentile: %{y:.1f}%<br>"
                    + "95% CI: %{customdata[2]:.1f}% - %{customdata[3]:.1f}%<br>"
                    + "CI Method: Wilson<extra></extra>"
                )
                custom_data = list(
                    zip(
                        valid_data["percentiles"],
                        strata_hover_info,
                        [ci or 0 for ci in valid_data["ci_lower"]],
                        [ci or 0 for ci in valid_data["ci_upper"]],
                    )
                )
            else:
                hover_template = (
                    "<b>Strata: %{customdata[1]}</b><br><br>"
                    + f"<b>{feature.replace('_', ' ').title()}</b><br>"
                    + "Percentile: %{y:.1f}%<extra></extra>"
                )
                custom_data = list(zip(valid_data["percentiles"], strata_hover_info))
        else:
            if valid_data["has_ci"]:
                hover_template = (
                    f"<b>{feature.replace('_', ' ').title()}</b><br>"
                    + "Percentile: %{y:.1f}%<br>"
                    + "95% CI: %{customdata[1]:.1f}% - %{customdata[2]:.1f}%<br>"
                    + "CI Method: Wilson<extra></extra>"
                )
                custom_data = list(
                    zip(
                        valid_data["percentiles"],
                        [ci or 0 for ci in valid_data["ci_lower"]],
                        [ci or 0 for ci in valid_data["ci_upper"]],
                    )
                )
            else:
                hover_template = (
                    f"<b>{feature.replace('_', ' ').title()}</b><br>"
                    + "Percentile: %{y:.1f}%<extra></extra>"
                )
                custom_data = list(zip(valid_data["percentiles"]))

        return hover_template, custom_data

    def _add_overall_percentile_trace(
        self,
        fig,
        subject_data,
        sessions,
        strata_sessions_map,
        show_confidence_intervals,
        features_to_plot,
    ):
        """Add overall percentile trace with distinctive styling"""
        if "overall_percentiles" not in subject_data:
            return

        overall_percentiles = subject_data["overall_percentiles"]
        overall_ci_lower = subject_data.get("overall_percentiles_ci_lower", [])
        overall_ci_upper = subject_data.get("overall_percentiles_ci_upper", [])

        logger.info(
            f"Adding overall percentile trace: {len(overall_percentiles)} values"
        )

        # Get valid overall percentile data
        valid_overall_data = self._get_valid_overall_percentile_data(
            sessions,
            overall_percentiles,
            overall_ci_lower,
            overall_ci_upper,
            show_confidence_intervals,
        )

        if not valid_overall_data["sessions"]:
            return

        # Add overall CI bands if available
        if valid_overall_data["has_ci"]:
            self._add_overall_confidence_intervals(fig, valid_overall_data)

        # Add main overall percentile trace
        self._add_overall_trace(
            fig, valid_overall_data, strata_sessions_map, features_to_plot
        )

    def _get_valid_overall_percentile_data(
        self,
        sessions,
        overall_percentiles,
        overall_ci_lower,
        overall_ci_upper,
        show_confidence_intervals,
    ):
        """Extract and validate overall percentile data"""
        has_overall_ci = (
            len(overall_ci_lower) == len(overall_percentiles)
            and len(overall_ci_upper) == len(overall_percentiles)
            and show_confidence_intervals
        )

        valid_sessions, valid_percentiles, valid_ci_lower, valid_ci_upper = (
            [],
            [],
            [],
            [],
        )

        for j, (session, percentile) in enumerate(zip(sessions, overall_percentiles)):
            if percentile is not None and not pd.isna(percentile) and percentile != -1:
                valid_sessions.append(session)
                valid_percentiles.append(percentile)

                if (
                    has_overall_ci
                    and j < len(overall_ci_lower)
                    and j < len(overall_ci_upper)
                ):
                    ci_lower = overall_ci_lower[j]
                    ci_upper = overall_ci_upper[j]

                    if (
                        ci_lower is not None
                        and not pd.isna(ci_lower)
                        and ci_lower != -1
                        and ci_upper is not None
                        and not pd.isna(ci_upper)
                        and ci_upper != -1
                    ):
                        valid_ci_lower.append(ci_lower)
                        valid_ci_upper.append(ci_upper)
                    else:
                        valid_ci_lower.append(None)
                        valid_ci_upper.append(None)

        return {
            "sessions": valid_sessions,
            "percentiles": valid_percentiles,
            "ci_lower": valid_ci_lower,
            "ci_upper": valid_ci_upper,
            "has_ci": has_overall_ci and len(valid_ci_lower) == len(valid_sessions),
        }

    def _add_overall_confidence_intervals(self, fig, valid_overall_data):
        """Add confidence interval bands for overall percentile"""
        # Filter CI data to match valid sessions
        valid_ci_lower = [ci for ci in valid_overall_data["ci_lower"] if ci is not None]
        valid_ci_upper = [ci for ci in valid_overall_data["ci_upper"] if ci is not None]
        valid_sessions_ci = [
            session
            for session, ci_lower, ci_upper in zip(
                valid_overall_data["sessions"],
                valid_overall_data["ci_lower"],
                valid_overall_data["ci_upper"],
            )
            if ci_lower is not None and ci_upper is not None
        ]

        if not valid_ci_lower:
            return

        # Add upper bound (invisible line)
        fig.add_trace(
            go.Scatter(
                x=valid_sessions_ci,
                y=valid_ci_upper,
                fill=None,
                mode="lines",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                hoverinfo="skip",
                name="overall_ci_upper",
            )
        )

        # Add lower bound with fill (sea green with transparency)
        fig.add_trace(
            go.Scatter(
                x=valid_sessions_ci,
                y=valid_ci_lower,
                fill="tonexty",
                mode="lines",
                line=dict(color="rgba(0,0,0,0)"),
                fillcolor="rgba(46, 139, 87, 0.2)",
                showlegend=False,
                hoverinfo="skip",
                name="overall_ci_band",
            )
        )

        logger.info(f"Added overall CI bands: {len(valid_sessions_ci)} sessions")

    def _add_overall_trace(
        self, fig, valid_overall_data, strata_sessions_map, features_to_plot
    ):
        """Add the main overall percentile trace"""
        # Create strata info for hover
        strata_hover_info = [
            strata_sessions_map.get(session, "Unknown")
            for session in valid_overall_data["sessions"]
        ]

        is_only_trace = len(features_to_plot) == 0

        # Create hover template
        if is_only_trace or not features_to_plot:
            if valid_overall_data["has_ci"]:
                hover_template = (
                    "<b>Strata: %{customdata[1]}</b><br><br>"
                    + "<b>Overall Percentile</b><br>"
                    + "Percentile: %{y:.1f}%<br>"
                    + "95% CI: %{customdata[2]:.1f}% - %{customdata[3]:.1f}%<br>"
                    + "CI Method: Wilson<extra></extra>"
                )
                custom_data = list(
                    zip(
                        valid_overall_data["percentiles"],
                        strata_hover_info,
                        [ci or 0 for ci in valid_overall_data["ci_lower"]],
                        [ci or 0 for ci in valid_overall_data["ci_upper"]],
                    )
                )
            else:
                hover_template = (
                    "<b>Strata: %{customdata[1]}</b><br><br>"
                    + "<b>Overall Percentile</b><br>"
                    + "Percentile: %{y:.1f}%<extra></extra>"
                )
                custom_data = list(
                    zip(valid_overall_data["percentiles"], strata_hover_info)
                )
        else:
            if valid_overall_data["has_ci"]:
                hover_template = (
                    "<b>Overall Percentile</b><br>"
                    + "Percentile: %{y:.1f}%<br>"
                    + "95% CI: %{customdata[1]:.1f}% - %{customdata[2]:.1f}%<br>"
                    + "CI Method: Wilson<extra></extra>"
                )
                custom_data = list(
                    zip(
                        valid_overall_data["percentiles"],
                        [ci or 0 for ci in valid_overall_data["ci_lower"]],
                        [ci or 0 for ci in valid_overall_data["ci_upper"]],
                    )
                )
            else:
                hover_template = (
                    "<b>Overall Percentile</b><br>"
                    + "Percentile: %{y:.1f}%<extra></extra>"
                )
                custom_data = list(zip(valid_overall_data["percentiles"]))

        # Add overall percentile trace with distinctive styling
        fig.add_trace(
            go.Scatter(
                x=valid_overall_data["sessions"],
                y=valid_overall_data["percentiles"],
                mode="lines",
                name="Overall Percentile",
                line=dict(
                    color="#2E8B57",
                    width=4,
                    dash="dash",
                    shape="spline",
                    smoothing=1.0,
                ),
                hovertemplate=hover_template,
                customdata=custom_data,
            )
        )

    def _configure_plot_layout(self, fig):
        """Configure the plot layout and reference lines"""
        # Add reference lines for percentile categories
        reference_lines = [
            (6.5, "red", "Severely Below (6.5%)"),
            (28, "orange", "Below (28%)"),
            (72, "orange", "Good (72%)"),
            (93.5, "green", "Severely Good (93.5%)"),
        ]

        for y_value, color, label in reference_lines:
            fig.add_hline(
                y=y_value,
                line_dash="dash",
                line_color=color,
                line_width=1,
                opacity=0.7,
                annotation_text=label,
                annotation_position="right",
            )

        # Update layout
        fig.update_layout(
            title=None,
            xaxis_title="Session Number",
            yaxis_title="Feature Percentiles (%)",
            template="plotly_white",
            margin=dict(l=40, r=20, t=40, b=60),
            height=550,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
            hovermode="x unified",
            xaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(211,211,211,0.3)"),
            yaxis=dict(
                range=[0, 100],
                showgrid=True,
                gridwidth=1,
                gridcolor="rgba(211,211,211,0.3)",
                zeroline=False,
            ),
        )

    def _add_plot_enhancements(self, fig, subject_data, sessions, highlighted_session):
        """Add plot enhancements like strata transitions, highlights, and outliers"""
        # Add strata transition lines
        strata_data = subject_data.get("strata", [])
        if strata_data and len(strata_data) == len(sessions):
            self._add_strata_transitions(fig, sessions, strata_data)

        # Add session highlight if specified
        if highlighted_session and sessions and highlighted_session in sessions:
            fig.add_vline(
                x=highlighted_session,
                line=dict(color="rgba(65, 105, 225, 0.6)", width=3, dash="solid"),
                annotation_text=f"Session {highlighted_session}",
                annotation_position="top",
            )

        # Add outlier markers
        self._add_outlier_markers(fig, sessions, subject_data.get("is_outlier", []))

    def _get_strata_abbreviation(self, strata):
        """Get abbreviated strata name for display"""
        return get_strata_abbreviation(strata)

    def _add_strata_transitions(self, fig, sessions, strata_data):
        """Add vertical lines for strata transitions"""
        if not strata_data or len(strata_data) != len(sessions):
            return

        # Find transition points
        transitions = []
        current_strata = None

        for i, (session, strata) in enumerate(zip(sessions, strata_data)):
            if current_strata is None:
                current_strata = strata
                transitions.append(
                    {"session": session, "strata": strata, "transition_type": "start"}
                )
            elif strata != current_strata:
                transitions.append(
                    {
                        "session": session,
                        "strata": strata,
                        "transition_type": "transition",
                    }
                )
                current_strata = strata

        # Add vertical lines for transitions
        for transition in transitions[1:]:
            session = transition["session"]
            strata = transition["strata"]
            strata_abbr = self._get_strata_abbreviation(strata)

            fig.add_vline(
                x=session,
                line=dict(color="rgba(128, 128, 128, 0.6)", width=2, dash="dash"),
                annotation=dict(
                    text=f"→ {strata_abbr}",
                    textangle=-90,
                    font=dict(size=10, color="gray"),
                    showarrow=False,
                    yshift=10,
                ),
            )

    def _hex_to_rgb(self, hex_color):
        """Convert hex color to RGB string for transparency"""
        hex_color = hex_color.lstrip("#")
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return f"{r}, {g}, {b}"
        except Exception:
            return "128, 128, 128"  # Default gray

    def _add_outlier_markers(self, fig, sessions, outlier_data):
        """
        Add purple markers for outlier sessions on the percentile time series plot

        Parameters:
            fig: plotly.graph_objects.Figure - The percentile time series figure
            sessions: list - List of session numbers
            outlier_data: list - List of boolean outlier indicators for each session
        """
        if not sessions or not outlier_data or len(outlier_data) != len(sessions):
            logger.info(
                "No outlier data available or length mismatch for percentile time series markers"
            )
            return

        outlier_sessions = []

        # Find outlier sessions
        for session, is_outlier in zip(sessions, outlier_data):
            if is_outlier:
                outlier_sessions.append(session)

        if not outlier_sessions:
            return

        # Add purple markers for outlier sessions
        fig.add_trace(
            go.Scatter(
                x=outlier_sessions,
                y=[95] * len(outlier_sessions),
                mode="markers",
                marker=dict(
                    color="#9C27B0",
                    size=12,
                    symbol="diamond",
                    line=dict(width=2, color="#FFFFFF"),
                ),
                name="Outlier Sessions",
                hovertemplate="<b>Outlier Session</b><br>Session: %{x}<extra></extra>",
                showlegend=True,
            )
        )

        logger.info(
            f"Added outlier markers to percentile plot for {len(outlier_sessions)} sessions: {outlier_sessions}"
        )
