package com.shuk.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.widget.RemoteViews
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class FpiWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        super.onUpdate(context, appWidgetManager, appWidgetIds)
        updateWidgetState(context)
        WidgetDataFetcher.fetchAndRender(context)
        schedulePeriodicUpdates(context)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_REFRESH) {
            WidgetDataFetcher.fetchAndRender(context)
        }
    }

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        schedulePeriodicUpdates(context)
    }

    override fun onDisabled(context: Context) {
        super.onDisabled(context)
        WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
    }

    private fun schedulePeriodicUpdates(context: Context) {
        val request = PeriodicWorkRequestBuilder<FpiWidgetUpdateWorker>(15, TimeUnit.MINUTES).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request
        )
    }

    companion object {
        const val ACTION_REFRESH = "com.shuk.widget.ACTION_REFRESH"
        private const val WORK_NAME = "fpi_widget_periodic_update"

        fun updateWidgetState(context: Context, total: String = "-", pnl: String = "-", cycle: String = "-") {
            val views = RemoteViews(context.packageName, R.layout.fpi_widget)
            views.setTextViewText(R.id.totalValue, total)
            views.setTextViewText(R.id.pnlPercent, pnl)
            views.setTextViewText(R.id.cycleValue, cycle)
            val pnlColor = when {
                pnl.startsWith("-") -> Color.parseColor("#E25A5A")
                pnl.startsWith("+") -> Color.parseColor("#3ECF8E")
                else -> Color.parseColor("#ECF5FF")
            }
            views.setTextColor(R.id.pnlPercent, pnlColor)

            val refreshIntent = Intent(context, FpiWidgetProvider::class.java).apply {
                action = ACTION_REFRESH
            }
            val refreshPendingIntent = PendingIntent.getBroadcast(
                context,
                1,
                refreshIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            views.setOnClickPendingIntent(R.id.rootWidget, refreshPendingIntent)

            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, FpiWidgetProvider::class.java))
            manager.updateAppWidget(ids, views)
        }
    }
}
