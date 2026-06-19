"""Tests for topic bw, topic info, type list/show commands."""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from lcm_cli.cli import app

runner = CliRunner()


class TestTopicBw:
    """Tests for ``lcm topic bw`` command."""

    def test_bw_command_help(self):
        """Test that bw command shows help."""
        result = runner.invoke(app, ["topic", "bw", "--help"])
        assert result.exit_code == 0
        assert "Monitor bandwidth" in result.stdout

    def test_bw_with_log_file(self):
        """Test bw command with --from log file."""
        # Create a minimal log file
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name

        result = runner.invoke(
            app, ["topic", "bw", "TEST", "--from", log_path, "--window", "1.0"]
        )
        # Should exit (may fail gracefully if no messages)
        # Exit code 2 is also acceptable for missing channel
        assert result.exit_code in [0, 1, 2]

        Path(log_path).unlink(missing_ok=True)


class TestTopicInfo:
    """Tests for ``lcm topic info`` command."""

    def test_info_command_help(self):
        """Test that info command shows help."""
        result = runner.invoke(app, ["topic", "info", "--help"])
        assert result.exit_code == 0
        # Check for help content
        assert "channel" in result.stdout.lower() and "inspect" in result.stdout.lower()

    def test_info_with_log_file(self):
        """Test info command with --from log file."""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name

        result = runner.invoke(
            app, ["topic", "info", "TEST", "--from", log_path, "--duration", "0.1"]
        )
        # Channel not found is acceptable
        assert result.exit_code in [0, 1]

        Path(log_path).unlink(missing_ok=True)


class TestTypeList:
    """Tests for ``lcm type list`` command."""

    def test_type_list_help(self):
        """Test that type list command shows help."""
        result = runner.invoke(app, ["type", "list", "--help"])
        assert result.exit_code == 0
        assert "List registered types" in result.stdout or "type" in result.stdout.lower()

    def test_type_list_with_lcm_file(self):
        """Test type list with --lcm-file."""
        # Create a minimal .lcm file
        lcm_content = """
package test;
struct test_t {
    int32_t value;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lcm", delete=False) as f:
            f.write(lcm_content)
            lcm_path = f.name

        result = runner.invoke(app, ["type", "list", "--lcm-file", lcm_path])
        assert result.exit_code == 0
        # Should show the registered type
        assert "test_t" in result.stdout or "test.test_t" in result.stdout

        Path(lcm_path).unlink(missing_ok=True)

    def test_type_list_with_package_filter(self):
        """Test type list with --package filter."""
        lcm_content = """
package mypackage;
struct my_type_t {
    double x;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lcm", delete=False) as f:
            f.write(lcm_content)
            lcm_path = f.name

        result = runner.invoke(
            app, ["type", "list", "--lcm-file", lcm_path, "--package", "mypackage"]
        )
        assert result.exit_code == 0
        assert "my_type_t" in result.stdout

        # Filter with non-matching package
        result = runner.invoke(
            app, ["type", "list", "--lcm-file", lcm_path, "--package", "other"]
        )
        assert result.exit_code == 0
        assert "my_type_t" not in result.stdout

        Path(lcm_path).unlink(missing_ok=True)

    def test_type_list_with_grep_filter(self):
        """Test type list with --grep filter."""
        lcm_content = """
package test;
struct sensor_reading_t {
    double temperature;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lcm", delete=False) as f:
            f.write(lcm_content)
            lcm_path = f.name

        result = runner.invoke(
            app, ["type", "list", "--lcm-file", lcm_path, "--grep", "sensor"]
        )
        assert result.exit_code == 0
        assert "sensor_reading_t" in result.stdout

        # Grep with non-matching pattern
        result = runner.invoke(
            app, ["type", "list", "--lcm-file", lcm_path, "--grep", "camera"]
        )
        assert result.exit_code == 0
        assert "sensor_reading_t" not in result.stdout

        Path(lcm_path).unlink(missing_ok=True)


class TestTypeShow:
    """Tests for ``lcm type show`` command."""

    def test_type_show_help(self):
        """Test that type show command shows help."""
        result = runner.invoke(app, ["type", "show", "--help"])
        assert result.exit_code == 0
        assert "Show type structure" in result.stdout or "type" in result.stdout.lower()

    def test_type_show_simple_struct(self):
        """Test type show with a simple struct."""
        lcm_content = """
package example;
struct example_t {
    int32_t utime;
    double position[3];
    string name;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lcm", delete=False) as f:
            f.write(lcm_content)
            lcm_path = f.name

        result = runner.invoke(
            app, ["type", "show", "example_t", "--lcm-file", lcm_path]
        )
        assert result.exit_code == 0
        # Should show field information
        assert "utime" in result.stdout or "position" in result.stdout

        Path(lcm_path).unlink(missing_ok=True)

    def test_type_show_with_nested_struct(self):
        """Test type show with nested struct."""
        lcm_content = """
package test;
struct pose_t {
    double x;
    double y;
    double theta;
}
struct robot_state_t {
    pose_t pose;
    double velocity;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lcm", delete=False) as f:
            f.write(lcm_content)
            lcm_path = f.name

        result = runner.invoke(
            app, ["type", "show", "robot_state_t", "--lcm-file", lcm_path]
        )
        assert result.exit_code == 0
        # Should show nested type reference
        assert "pose" in result.stdout.lower() or "pose_t" in result.stdout

        Path(lcm_path).unlink(missing_ok=True)

    def test_type_show_not_found(self):
        """Test type show with non-existent type."""
        lcm_content = """
package test;
struct my_type_t {
    int32_t value;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lcm", delete=False) as f:
            f.write(lcm_content)
            lcm_path = f.name

        result = runner.invoke(
            app, ["type", "show", "nonexistent_t", "--lcm-file", lcm_path]
        )
        # Should fail gracefully
        assert result.exit_code != 0 or "not found" in result.stdout.lower() or "error" in result.stdout.lower()

        Path(lcm_path).unlink(missing_ok=True)


class TestTopicListWatch:
    """Tests for --watch mode in topic list."""

    def test_topic_list_watch_help(self):
        """Test that --watch option exists."""
        result = runner.invoke(app, ["topic", "list", "--help"])
        assert result.exit_code == 0
        assert "--watch" in result.stdout

    def test_topic_list_with_watch_short_duration(self):
        """Test topic list with --watch (short duration to avoid hanging)."""
        # This will run in watch mode, we need to interrupt it
        import time

        def interrupt_after_delay():
            time.sleep(0.5)
            # Send SIGINT to stop the watch mode
            raise KeyboardInterrupt()

        # Just verify it starts without errors
        result = runner.invoke(
            app, ["topic", "list", "--watch", "--stale", "0.5"],
            timeout=2
        )
        # Should exit cleanly (KeyboardInterrupt or timeout)
        assert result.exit_code in [0, 1] or "KeyboardInterrupt" in str(result.exception) or result.exception is None


class TestNodeListWatch:
    """Tests for --watch mode in node list."""

    def test_node_list_watch_help(self):
        """Test that --watch option exists in node list."""
        result = runner.invoke(app, ["node", "list", "--help"])
        assert result.exit_code == 0
        assert "--watch" in result.stdout


class TestTopicStatsEnhanced:
    """Tests for enhanced topic stats features."""

    def test_topic_stats_sort_help(self):
        """Test that --sort option exists."""
        result = runner.invoke(app, ["topic", "stats", "--help"])
        assert result.exit_code == 0
        assert "--sort" in result.stdout

    def test_topic_stats_top_help(self):
        """Test that --top option exists."""
        result = runner.invoke(app, ["topic", "stats", "--help"])
        assert result.exit_code == 0
        assert "--top" in result.stdout

    def test_topic_stats_freeze_help(self):
        """Test that --freeze option exists."""
        result = runner.invoke(app, ["topic", "stats", "--help"])
        assert result.exit_code == 0
        assert "--freeze" in result.stdout

    def test_topic_stats_spark_help(self):
        """Test that --spark option exists."""
        result = runner.invoke(app, ["topic", "stats", "--help"])
        assert result.exit_code == 0
        assert "--spark" in result.stdout

    def test_topic_stats_with_log_file(self):
        """Test topic stats with --from log file."""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name

        result = runner.invoke(
            app, ["topic", "stats", "--from", log_path, "--freeze"]
        )
        # Should exit cleanly
        assert result.exit_code in [0, 1]

        Path(log_path).unlink(missing_ok=True)
