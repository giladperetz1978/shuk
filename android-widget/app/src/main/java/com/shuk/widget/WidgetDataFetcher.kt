package com.shuk.widget

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

object WidgetDataFetcher {
    private const val API_URL = "https://144-91-96-77.nip.io/api/summary"

    fun fetchAndRender(context: Context) {
        val (total, pnl, cycle) = try {
            val response = httpGet(API_URL)
            val json = JSONObject(response)
            val latest = json.optJSONObject("latest_snapshot")
            if (latest == null) {
                Triple("-", "-", "-")
            } else {
                val value = latest.optDouble("value", Double.NaN)
                val pnlPct = latest.optDouble("pnl_pct", Double.NaN)
                val cycleNum = latest.optInt("cycle", -1)

                val totalStr = if (value.isNaN()) "-" else String.format(Locale.US, "$%,.2f", value)
                val pnlStr = if (pnlPct.isNaN()) "-" else String.format(Locale.US, "%+.2f%%", pnlPct)
                val cycleStr = if (cycleNum < 0) "-" else cycleNum.toString()
                Triple(totalStr, pnlStr, cycleStr)
            }
        } catch (_: Exception) {
            Triple("-", "-", "-")
        }

        FpiWidgetProvider.updateWidgetState(context, total, pnl, cycle)
    }

    private fun httpGet(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = "GET"
        conn.connectTimeout = 8000
        conn.readTimeout = 8000
        conn.setRequestProperty("Accept", "application/json")

        return conn.inputStream.bufferedReader().use { it.readText() }
    }
}
