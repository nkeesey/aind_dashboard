"""
Subject percentile heatmap visualization component for AIND Dashboard

This module creates interactive heatmap visualizations showing percentile data
across sessions with strata transitions and outlier highlighting.
"""

import plotly.graph_objects as go
from dash import dcc

from app_utils.simple_logger import get_logger
from app_utils.strata_utils import get_strata_abbreviation

logger = get_logger("subject_percentile_heatmap")


class AppSubjectPercentileHeatmap:
    def __init__(self):

        # Features configuration
        self.features_config = {
            "finished_trials": False,  # Higher is better
            "ignore_rate": True,  # Lower is better
            "total_trials": False,  # Higher is better
            "foraging_performance": False,  # Higher is better
            "abs(bias_naive)": True,  # Lower is better
        }

    def build(
        self,
        subject_id=None,
        app_utils=None,
        highlighted_session=None,
        colorscale_mode="binned",
    ):
        """
        Build percentile heatmap showing progression over time including overall percentile

        This method coordinates UI rendering by calling business logic functions for data processing
        and statistical calculations, keeping the component focused on visualization concerns.

        Parameters:
            subject_id (str): Subject ID to build heatmap for
            app_utils (AppUtils): App utilities instance for accessing cached data
            highlighted_session (int): Session number to highlight with light blue border
            colorscale_mode (str): Either "binned" or "continuous" for colorscale type

        Returns:
            dcc.Graph: Heatmap showing percentile progression over time
        """
        if highlighted_session:
            logger.info(f"Highlighting session: {highlighted_session}")

        if not subject_id or not app_utils:
            return self._create_empty_heatmap("No subject selected")

        # Get time series data from UI cache
        time_series_data = app_utils.get_time_series_data(subject_id, use_cache=True)

        if not time_series_data or not time_series_data.get("sessions"):
            return self._create_empty_heatmap("No session data available")

        # Extract session data
        sessions = time_series_data["sessions"]

        # Process data using business logic functions
        from app_utils.app_analysis.statistical_utils import StatisticalUtils
        from app_utils.percentile_utils import calculate_heatmap_colorscale

        # Extract and validate heatmap matrix data
        heatmap_data, feature_names = StatisticalUtils.process_heatmap_matrix_data(
            time_series_data, self.features_config
        )

        # Create session labels
        session_labels = [f"S{s}" for s in sessions]
        logger.info(f"Displaying all {len(sessions)} sessions in heatmap")

        if not heatmap_data or not feature_names:
            return self._create_empty_heatmap("No valid feature data")

        # Get colorscale using business logic
        colorscale = calculate_heatmap_colorscale(colorscale_mode)

        # Create the heatmap visualization
        fig = go.Figure(
            data=go.Heatmap(
                z=heatmap_data,
                x=session_labels,
                y=feature_names,
                colorscale=colorscale,
                zmin=0,
                zmax=100,
                hoverongaps=False,
                hovertemplate="<b>%{y}</b><br>Session: %{x}<br>Percentile: %{z:.1f}%<extra></extra>",
                showscale=True,
                colorbar=dict(
                    title=dict(text="Percentile", side="right"),
                    thickness=15,
                    len=0.7,
                    x=1.02,
                ),
            )
        )

        # Add highlighting for selected session
        if highlighted_session is not None and highlighted_session in sessions:
            session_idx = StatisticalUtils.calculate_session_highlighting_coordinates(
                sessions, highlighted_session
            )

            if session_idx is not None:
                fig.add_shape(
                    type="rect",
                    x0=session_idx - 0.4,
                    x1=session_idx + 0.4,
                    y0=-0.5,
                    y1=len(feature_names) - 0.5,
                    line=dict(
                        color="#4A90E2",
                        width=3,
                    ),
                    fillcolor="rgba(74, 144, 226, 0.1)",
                    layer="above",
                )

        # Add strata boundaries
        self._add_strata_boundaries(
            fig, sessions, time_series_data.get("strata", []), len(feature_names)
        )

        # Add outlier markers to heatmap
        self._add_outlier_markers(
            fig, sessions, time_series_data.get("is_outlier", []), len(feature_names)
        )

        fig.update_layout(
            title=None,
            xaxis_title="Session",
            yaxis_title=None,
            margin=dict(l=10, r=60, t=10, b=30),
            height=300,
            font=dict(size=9),
            plot_bgcolor="white",
            xaxis=dict(
                tickangle=-45,
                tickfont=dict(size=8),
                automargin=True,
            ),
            yaxis=dict(tickfont=dict(size=10), automargin=True),
        )

        return dcc.Graph(
            id="percentile-heatmap",
            figure=fig,
            config={"displayModeBar": False},
            style={"height": "300px", "width": "100%"},
        )

    def _create_custom_colorscale(self):
        from app_utils.percentile_utils import calculate_heatmap_colorscale

        return calculate_heatmap_colorscale("binned")

    def _create_continuous_colorscale(self):
        from app_utils.percentile_utils import calculate_heatmap_colorscale

        return calculate_heatmap_colorscale("continuous")

    def _create_empty_heatmap(self, message):
        """Create empty heatmap with message"""
        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14, color="#666666"),
        )
        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=300,
            plot_bgcolor="white",
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(showgrid=False, showticklabels=False),
        )

        return dcc.Graph(
            id="percentile-heatmap",
            figure=fig,
            config={"displayModeBar": False},
            style={"height": "300px", "width": "100%"},
        )

    def _add_strata_boundaries(self, fig, sessions, strata_data, num_feature_rows):
        """
        Add vertical lines for strata transitions in the heatmap

        Parameters:
            fig: plotly.graph_objects.Figure - The heatmap figure
            sessions: list - List of session numbers
            strata_data: list - List of strata for each session
            num_feature_rows: int - Number of feature rows in the heatmap
        """
        if not strata_data or len(strata_data) != len(sessions):
            logger.info("No strata data available or length mismatch")
            return

        # Find transition points
        transitions = []
        current_strata = None

        for i, (session, strata) in enumerate(zip(sessions, strata_data)):
            if current_strata is None:
                current_strata = strata
                transitions.append(
                    {
                        "session_idx": i,
                        "session": session,
                        "strata": strata,
                        "transition_type": "start",
                    }
                )
            elif strata != current_strata:
                transitions.append(
                    {
                        "session_idx": i,
                        "session": session,
                        "strata": strata,
                        "transition_type": "transition",
                    }
                )
                current_strata = strata

        logger.info(
            f"Found {len(transitions)} strata transitions: {[t['session'] for t in transitions]}"
        )

        # Add vertical lines for transitions
        for transition in transitions[1:]:
            session_idx = transition["session_idx"]
            session = transition["session"]
            strata = transition["strata"]
            strata_abbr = self._get_strata_abbreviation(strata)

            fig.add_shape(
                type="line",
                x0=session_idx - 0.5,
                x1=session_idx - 0.5,
                y0=-0.5,
                y1=num_feature_rows - 0.5,
                line=dict(
                    color="rgba(128, 128, 128, 0.8)",
                    width=2,
                    dash="dash",
                ),
                layer="above",
            )

            # Add text annotation for the new strata
            fig.add_annotation(
                x=session_idx - 0.5,
                y=num_feature_rows - 0.2,
                text=f"→ {strata_abbr}",
                showarrow=False,
                font=dict(size=8, color="gray"),
                textangle=-90,
                xanchor="center",
                yanchor="bottom",
            )

            logger.info(
                f"Added strata boundary at session {session} (index {session_idx}) for strata: {strata_abbr}"
            )

    def _get_strata_abbreviation(self, strata):
        """Get abbreviated strata name for display (same as time series)"""
        return get_strata_abbreviation(strata)

    def _add_outlier_markers(self, fig, sessions, outlier_data, num_feature_rows):
        """
        Add outlier markers to the heatmap by highlighting outlier session columns

        Parameters:
            fig: plotly.graph_objects.Figure - The heatmap figure
            sessions: list - List of session numbers
            outlier_data: list - List of outlier indicators for each session
            num_feature_rows: int - Number of feature rows in the heatmap
        """
        if not outlier_data or len(outlier_data) != len(sessions):
            logger.info("No outlier data available or length mismatch")
            return

        outlier_count = 0

        # Add vertical rectangles for outlier sessions
        for session_idx, (session, is_outlier) in enumerate(
            zip(sessions, outlier_data)
        ):
            if is_outlier:
                # Add a rectangle with purple border around the entire column for this session
                fig.add_shape(
                    type="rect",
                    x0=session_idx - 0.45,
                    x1=session_idx + 0.45,
                    y0=-0.45,
                    y1=num_feature_rows - 0.55,
                    line=dict(
                        color="#9C27B0",
                        width=2,
                    ),
                    fillcolor="rgba(156, 39, 176, 0.1)",
                    layer="above",
                )
                outlier_count += 1

        if outlier_count > 0:
            logger.info(
                f"Added outlier markers for {outlier_count} sessions with purple borders"
            )
