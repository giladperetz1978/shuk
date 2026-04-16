package com.shuk.monitor

import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.DecimalFormat
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val apiUrl = "https://144-91-96-77.nip.io/api/summary"
    private val handler = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor()

    private lateinit var valueText: TextView
    private lateinit var pnlText: TextView
    private lateinit var cycleText: TextView
    private lateinit var statusText: TextView

    private val refreshRunnable = object : Runnable {
        override fun run() {
            fetchSummary()
            handler.postDelayed(this, 15_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        valueText = findViewById(R.id.valueText)
        pnlText = findViewById(R.id.pnlText)
        cycleText = findViewById(R.id.cycleText)
        statusText = findViewById(R.id.statusText)

        findViewById<TextView>(R.id.refreshBtn).setOnClickListener {
            fetchSummary()
        }
    }

    override fun onStart() {
        super.onStart()
        refreshRunnable.run()
    }

    override fun onStop() {
        super.onStop()
        handler.removeCallbacks(refreshRunnable)
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
    }

    private fun fetchSummary() {
        statusText.text = "מעדכן..."
        executor.execute {
            try {
                val json = JSONObject(httpGet(apiUrl))
                val latest = json.optJSONObject("latest_snapshot")
                if (latest == null) {
                    runOnUiThread {
                        statusText.text = "אין נתונים עדיין"
                    }
                    return@execute
                }

                val value = latest.optDouble("value", Double.NaN)
                val pnlPct = latest.optDouble("pnl_pct", Double.NaN)
                val cycle = latest.optInt("cycle", -1)
                val serverTs = latest.optString("ts", "")

                runOnUiThread {
                    valueText.text = formatMoney(value)
                    pnlText.text = formatPercent(pnlPct)
                    cycleText.text = if (cycle >= 0) cycle.toString() else "-"
                    pnlText.setTextColor(
                        when {
                            pnlPct.isNaN() -> Color.parseColor("#ECF5FF")
                            pnlPct < 0 -> Color.parseColor("#E25A5A")
                            else -> Color.parseColor("#3ECF8E")
                        }
                    )
                    val localRefresh = java.time.LocalTime.now().withNano(0)
                    val serverPart = if (serverTs.isNotBlank()) "זמן שרת: $serverTs" else "זמן שרת: -"
                    statusText.text = "$serverPart | רענון מקומי: $localRefresh"
                }
            } catch (_: Exception) {
                runOnUiThread {
                    statusText.text = "שגיאת חיבור לשרת"
                }
            }
        }
    }

    private fun httpGet(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = "GET"
        conn.connectTimeout = 8000
        conn.readTimeout = 8000
        conn.setRequestProperty("Accept", "application/json")
        return conn.inputStream.bufferedReader().use { it.readText() }
    }

    private fun formatMoney(v: Double): String {
        if (v.isNaN()) return "-"
        val df = DecimalFormat("#,##0.00")
        return "$${df.format(v)}"
    }

    private fun formatPercent(v: Double): String {
        if (v.isNaN()) return "-"
        return String.format(Locale.US, "%+.2f%%", v)
    }
}
