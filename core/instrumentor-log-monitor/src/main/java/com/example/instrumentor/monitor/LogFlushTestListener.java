package com.example.instrumentor.monitor;

import org.junit.platform.launcher.TestExecutionListener;
import org.junit.platform.launcher.TestPlan;

/**
 * JUnit Platform Listener: automatically flushes logs after all tests finish.
 *
 * This approach does not rely on JVM shutdown hooks, so it works regardless of
 * whether Surefire uses halt() or exit(), ensuring logs are written to disk
 * after test execution completes.
 */
public class LogFlushTestListener implements TestExecutionListener {

    @Override
    public void testPlanExecutionFinished(TestPlan testPlan) {
        System.err.println("[LogFlushTestListener] All tests finished, flushing logs...");
        try {
            LogMonitorServer.flushNow("junit-listener");
        } catch (Exception e) {
            System.err.println("[LogFlushTestListener] Flush failed: " + e.getMessage());
            e.printStackTrace();
        }
    }
}