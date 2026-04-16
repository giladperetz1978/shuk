package com.shuk.widget

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

class FpiWidgetUpdateWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {
    override suspend fun doWork(): Result {
        return try {
            WidgetDataFetcher.fetchAndRender(applicationContext)
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }
}
