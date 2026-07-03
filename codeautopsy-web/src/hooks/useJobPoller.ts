import { useRef, useCallback } from 'react';
import { apiClient } from '../api/client';

/**
 * useJobPoller — Fix: replace the single shared activePollerRef with a
 * Map<jobId, intervalId> so that concurrent polls (e.g. diagram + story
 * running in parallel via Promise.all) each maintain independent intervals.
 *
 * Previously a shared `activePollerRef` was cleared by the second poll
 * invocation, silently killing the first one and causing the IngestionConsole
 * to stall at 80% indefinitely.
 */
export function useJobPoller() {
  // Map of jobId → setInterval handle so multiple jobs can poll concurrently
  const pollerMapRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  const stopPollingJob = useCallback((jobId: string) => {
    const handle = pollerMapRef.current.get(jobId);
    if (handle !== undefined) {
      clearInterval(handle);
      pollerMapRef.current.delete(jobId);
    }
  }, []);

  const stopPolling = useCallback(() => {
    // Clear ALL active pollers (used on unmount)
    pollerMapRef.current.forEach((handle) => clearInterval(handle));
    pollerMapRef.current.clear();
  }, []);

  const pollJobStatus = useCallback((
    jobId: string,
    phaseName: string,
    onStepChange: (step: string) => void,
    onProgressChange: (progress: number) => void
  ): Promise<string> => {
    // Stop any pre-existing poller for this specific job ID
    stopPollingJob(jobId);

    return new Promise((resolve, reject) => {
      let lastStep = '';

      const intervalHandle = setInterval(async () => {
        try {
          const statusRes = await apiClient.pollJob(jobId);

          if (statusRes.current_step && statusRes.current_step !== lastStep) {
            lastStep = statusRes.current_step;
            onStepChange(lastStep);
          }

          // Calculate cumulative pipeline progress based on active phase
          let cumulativeProgress = statusRes.progress_percent;
          if (phaseName === 'parse') {
            cumulativeProgress = 30 + Math.floor(statusRes.progress_percent * 0.25); // 0-100 → 30-55
          } else if (phaseName === 'chunk') {
            cumulativeProgress = 55 + Math.floor(statusRes.progress_percent * 0.25); // 0-100 → 55-80
          } else if (phaseName === 'diagram' || phaseName === 'story') {
            cumulativeProgress = 80 + Math.floor(statusRes.progress_percent * 0.2);  // 0-100 → 80-100
          } else {
            cumulativeProgress = Math.floor(statusRes.progress_percent * 0.3);       // 0-100 → 0-30 (ingest)
          }

          onProgressChange(cumulativeProgress);

          if (statusRes.status === 'complete') {
            stopPollingJob(jobId);
            resolve(statusRes.repo_key);
          } else if (statusRes.status === 'failed') {
            stopPollingJob(jobId);
            reject(new Error(statusRes.error || `${phaseName} job failed.`));
          }
        } catch (err: any) {
          stopPollingJob(jobId);
          reject(err);
        }
      }, 1200);

      // Register the interval under this job's ID
      pollerMapRef.current.set(jobId, intervalHandle);
    });
  }, [stopPollingJob]);

  return { pollJobStatus, stopPolling };
}
