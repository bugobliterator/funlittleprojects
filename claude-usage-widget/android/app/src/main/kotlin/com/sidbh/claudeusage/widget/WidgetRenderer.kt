package com.sidbh.claudeusage.widget

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BlurMaskFilter
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import com.sidbh.claudeusage.R
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

object WidgetRenderer {

    private const val ORANGE = 0xFFD97757.toInt()
    private const val ORANGE_SOFT = 0xFFF4A78A.toInt()
    private const val ORANGE_GLOW = 0x66D97757
    private const val WHITE = 0xFFF5F5F7.toInt()
    private const val WHITE_60 = 0x99F5F5F7.toInt()
    private const val WHITE_45 = 0x73F5F5F7.toInt()
    private const val WHITE_TRACK = 0x1AFFFFFF
    private const val CARD_BG = 0x0DFFFFFF
    private const val CARD_BORDER = 0x14FFFFFF
    private const val CARD_PEACH = 0xFFFFB892.toInt()

    fun render(context: Context, widthDp: Int, heightDp: Int, state: WidgetState.Loaded): Bitmap {
        val density = context.resources.displayMetrics.density
        val widthPx = (max(widthDp, 200) * density).toInt()
        val heightPx = (max(heightDp, 100) * density).toInt()

        val bitmap = Bitmap.createBitmap(widthPx, heightPx, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)

        val pad = 16f * density
        val headerHeight = 24f * density
        val gap = 10f * density

        drawHeader(canvas, paint, density, widthPx.toFloat(), pad, state)

        val bodyTop = pad + headerHeight + gap
        val bodyBottom = heightPx - pad
        val bodyLeft = pad
        val bodyRight = widthPx - pad
        val bodyHeight = bodyBottom - bodyTop
        val bodyWidth = bodyRight - bodyLeft

        // Determine layout: wide widget keeps 3-column row; narrow goes to 2-row stacked.
        val aspectRatio = bodyWidth / bodyHeight
        val twoRowLayout = aspectRatio < 1.7f

        if (twoRowLayout) {
            val countdownHeight = 56f * density
            val ringsHeight = bodyHeight - countdownHeight - gap

            val ringCellWidth = (bodyWidth - gap) / 2f
            drawRingGauge(
                canvas, paint, density,
                cellLeft = bodyLeft, cellTop = bodyTop, cellWidth = ringCellWidth, cellHeight = ringsHeight,
                percent = state.fiveHourPct,
                label = context.getString(R.string.ring_label_5h),
                sub = formatRingSubFiveHour(state.fiveHourResetsAt),
                empty = false,
            )
            val sevenDayPct = state.sevenDayPct
            drawRingGauge(
                canvas, paint, density,
                cellLeft = bodyLeft + ringCellWidth + gap, cellTop = bodyTop,
                cellWidth = ringCellWidth, cellHeight = ringsHeight,
                percent = sevenDayPct ?: 0.0,
                label = state.sevenDayLabel,
                sub = if (sevenDayPct == null) context.getString(R.string.placeholder_no_data)
                      else formatRingSubSevenDay(state.sevenDayResetsAt),
                empty = sevenDayPct == null,
            )

            drawCountdownStrip(
                canvas, paint, density, context,
                cellLeft = bodyLeft, cellTop = bodyTop + ringsHeight + gap,
                cellWidth = bodyWidth, cellHeight = countdownHeight,
                resetsAt = state.fiveHourResetsAt,
                barPercent = state.fiveHourPct,
            )
        } else {
            val cellWidth = (bodyWidth - 2 * gap) / 3f
            drawRingGauge(
                canvas, paint, density,
                cellLeft = bodyLeft, cellTop = bodyTop, cellWidth = cellWidth, cellHeight = bodyHeight,
                percent = state.fiveHourPct,
                label = context.getString(R.string.ring_label_5h),
                sub = formatRingSubFiveHour(state.fiveHourResetsAt),
                empty = false,
            )
            val sevenDayPct = state.sevenDayPct
            drawRingGauge(
                canvas, paint, density,
                cellLeft = bodyLeft + cellWidth + gap, cellTop = bodyTop,
                cellWidth = cellWidth, cellHeight = bodyHeight,
                percent = sevenDayPct ?: 0.0,
                label = state.sevenDayLabel,
                sub = if (sevenDayPct == null) context.getString(R.string.placeholder_no_data)
                      else formatRingSubSevenDay(state.sevenDayResetsAt),
                empty = sevenDayPct == null,
            )
            drawCountdownCard(
                canvas, paint, density, context,
                cellLeft = bodyLeft + 2 * (cellWidth + gap), cellTop = bodyTop,
                cellWidth = cellWidth, cellHeight = bodyHeight,
                resetsAt = state.fiveHourResetsAt,
                barPercent = state.fiveHourPct,
            )
        }

        if (state.mock) {
            drawMockBadge(canvas, paint, density, widthPx.toFloat(), heightPx.toFloat())
        }

        return bitmap
    }

    private fun drawCountdownStrip(
        canvas: Canvas, paint: Paint, density: Float, context: Context,
        cellLeft: Float, cellTop: Float, cellWidth: Float, cellHeight: Float,
        resetsAt: Instant?, barPercent: Double,
    ) {
        val cardRadius = 14f * density
        paint.style = Paint.Style.FILL
        paint.color = CARD_BG
        canvas.drawRoundRect(cellLeft, cellTop, cellLeft + cellWidth, cellTop + cellHeight, cardRadius, cardRadius, paint)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 1f * density
        paint.color = CARD_BORDER
        canvas.drawRoundRect(cellLeft, cellTop, cellLeft + cellWidth, cellTop + cellHeight, cardRadius, cardRadius, paint)

        val innerLeft = cellLeft + 12f * density
        val innerRight = cellLeft + cellWidth - 12f * density

        // Top line: label + big time.
        paint.style = Paint.Style.FILL
        paint.color = WHITE_45
        paint.textSize = 10f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        paint.textAlign = Paint.Align.LEFT
        val labelY = cellTop + 18f * density
        canvas.drawText(
            context.getString(R.string.countdown_label_resets_in).uppercase(Locale.getDefault()),
            innerLeft, labelY, paint,
        )

        paint.color = CARD_PEACH
        paint.textSize = 18f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        val countdownText = formatCountdown(resetsAt)
        paint.textAlign = Paint.Align.RIGHT
        canvas.drawText(countdownText, innerRight, labelY + 2f * density, paint)

        // Progress bar at bottom.
        val barLeft = innerLeft
        val barRight = innerRight
        val barHeight = 4f * density
        val barTop = cellTop + cellHeight - 12f * density - barHeight
        paint.style = Paint.Style.FILL
        paint.color = WHITE_TRACK
        canvas.drawRoundRect(barLeft, barTop, barRight, barTop + barHeight, barHeight / 2f, barHeight / 2f, paint)
        if (barPercent > 0) {
            val pct = (barPercent / 100.0).coerceIn(0.0, 1.0).toFloat()
            paint.color = ORANGE
            canvas.drawRoundRect(
                barLeft, barTop,
                barLeft + (barRight - barLeft) * pct, barTop + barHeight,
                barHeight / 2f, barHeight / 2f, paint,
            )
        }
    }

    private fun drawHeader(
        canvas: Canvas, paint: Paint, density: Float,
        widthPx: Float, pad: Float, state: WidgetState.Loaded,
    ) {
        val logoSize = 18f * density
        val logoLeft = pad
        val logoTop = pad
        val cornerRadius = 5f * density

        paint.style = Paint.Style.FILL
        paint.color = ORANGE
        canvas.drawRoundRect(
            logoLeft, logoTop, logoLeft + logoSize, logoTop + logoSize,
            cornerRadius, cornerRadius, paint,
        )

        paint.color = Color.WHITE
        paint.textSize = 11f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        paint.textAlign = Paint.Align.CENTER
        canvas.drawText(
            "C",
            logoLeft + logoSize / 2f,
            logoTop + logoSize / 2f + paint.textSize / 3f,
            paint,
        )

        paint.color = WHITE
        paint.textSize = 13f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        paint.textAlign = Paint.Align.LEFT
        val titleX = logoLeft + logoSize + 8f * density
        val titleBaseline = logoTop + logoSize / 2f + 5f * density
        canvas.drawText("Claude Usage", titleX, titleBaseline, paint)

        paint.textSize = 11f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
        paint.color = WHITE_60
        paint.textAlign = Paint.Align.RIGHT
        val time = state.fetchedAt.atZone(ZoneId.systemDefault())
            .format(DateTimeFormatter.ofPattern("HH:mm", Locale.getDefault()))
        val mockSuffix = if (state.mock) " · MOCK" else ""
        canvas.drawText("Opus · $time$mockSuffix", widthPx - pad, titleBaseline, paint)
    }

    private fun drawRingGauge(
        canvas: Canvas, paint: Paint, density: Float,
        cellLeft: Float, cellTop: Float, cellWidth: Float, cellHeight: Float,
        percent: Double, label: String, sub: String, empty: Boolean,
    ) {
        val ringDiameter = min(84f * density, min(cellWidth, cellHeight - 36f * density))
        val ringRadius = ringDiameter / 2f
        val stroke = 9f * density

        val cx = cellLeft + cellWidth / 2f
        val cy = cellTop + ringRadius + 2f * density

        paint.style = Paint.Style.STROKE
        paint.strokeWidth = stroke
        paint.color = WHITE_TRACK
        paint.strokeCap = Paint.Cap.BUTT
        canvas.drawCircle(cx, cy, ringRadius - stroke / 2f, paint)

        if (!empty && percent > 0) {
            val sweep = (360.0 * (percent / 100.0)).toFloat().coerceIn(0f, 360f)
            val rect = RectF(
                cx - ringRadius + stroke / 2f,
                cy - ringRadius + stroke / 2f,
                cx + ringRadius - stroke / 2f,
                cy + ringRadius - stroke / 2f,
            )

            paint.color = ORANGE_GLOW
            paint.maskFilter = BlurMaskFilter(8f * density, BlurMaskFilter.Blur.NORMAL)
            canvas.drawArc(rect, -90f, sweep, false, paint)
            paint.maskFilter = null

            paint.color = ORANGE
            paint.strokeCap = Paint.Cap.ROUND
            canvas.drawArc(rect, -90f, sweep, false, paint)
            paint.strokeCap = Paint.Cap.BUTT
        }

        paint.style = Paint.Style.FILL
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        paint.textAlign = Paint.Align.CENTER

        if (empty) {
            paint.color = WHITE_45
            paint.textSize = 14f * density
            canvas.drawText("—", cx, cy + paint.textSize / 3f, paint)
        } else {
            paint.color = WHITE
            paint.textSize = 17f * density
            canvas.drawText("${percent.toInt()}%", cx, cy + paint.textSize / 3f, paint)
        }

        val labelY = cy + ringRadius + 14f * density
        paint.color = WHITE_60
        paint.textSize = 10f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        canvas.drawText(label.uppercase(Locale.getDefault()), cx, labelY, paint)

        val subY = labelY + 12f * density
        paint.color = WHITE_45
        paint.textSize = 9f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
        val (line1, line2) = splitSub(sub)
        canvas.drawText(line1, cx, subY, paint)
        if (line2.isNotEmpty()) {
            canvas.drawText(line2, cx, subY + 11f * density, paint)
        }
    }

    private fun splitSub(sub: String): Pair<String, String> {
        val parts = sub.split('\n', limit = 2)
        return if (parts.size == 2) parts[0] to parts[1] else sub to ""
    }

    private fun drawCountdownCard(
        canvas: Canvas, paint: Paint, density: Float, context: Context,
        cellLeft: Float, cellTop: Float, cellWidth: Float, cellHeight: Float,
        resetsAt: Instant?, barPercent: Double,
    ) {
        val cardRadius = 16f * density

        paint.style = Paint.Style.FILL
        paint.color = CARD_BG
        canvas.drawRoundRect(cellLeft, cellTop, cellLeft + cellWidth, cellTop + cellHeight, cardRadius, cardRadius, paint)

        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 1f * density
        paint.color = CARD_BORDER
        canvas.drawRoundRect(cellLeft, cellTop, cellLeft + cellWidth, cellTop + cellHeight, cardRadius, cardRadius, paint)

        val cx = cellLeft + cellWidth / 2f
        val innerTop = cellTop + 12f * density
        val innerBottom = cellTop + cellHeight - 12f * density

        paint.style = Paint.Style.FILL
        paint.color = WHITE_45
        paint.textSize = 10f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        paint.textAlign = Paint.Align.CENTER
        canvas.drawText(
            context.getString(R.string.countdown_label_resets_in).uppercase(Locale.getDefault()),
            cx, innerTop + 10f * density, paint,
        )

        val countdownText = formatCountdown(resetsAt)
        paint.color = CARD_PEACH
        paint.textSize = 22f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        canvas.drawText(countdownText, cx, innerTop + 36f * density, paint)

        paint.color = WHITE_45
        paint.textSize = 9f * density
        paint.typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
        canvas.drawText(
            context.getString(R.string.countdown_scope_5h),
            cx, innerTop + 50f * density, paint,
        )

        val barLeft = cellLeft + 14f * density
        val barRight = cellLeft + cellWidth - 14f * density
        val barTop = innerBottom - 5f * density
        val barHeight = 3f * density

        paint.style = Paint.Style.FILL
        paint.color = WHITE_TRACK
        canvas.drawRoundRect(barLeft, barTop, barRight, barTop + barHeight, barHeight / 2f, barHeight / 2f, paint)

        if (barPercent > 0) {
            val pct = (barPercent / 100.0).coerceIn(0.0, 1.0).toFloat()
            paint.color = ORANGE
            canvas.drawRoundRect(
                barLeft, barTop,
                barLeft + (barRight - barLeft) * pct, barTop + barHeight,
                barHeight / 2f, barHeight / 2f, paint,
            )
        }
    }

    private fun drawMockBadge(canvas: Canvas, paint: Paint, density: Float, w: Float, h: Float) {
        // discreet badge top-right corner; "Opus · HH:mm · MOCK" already shows in header,
        // this dot reinforces it visually.
        val r = 4f * density
        paint.style = Paint.Style.FILL
        paint.color = 0xFFFBBF24.toInt()
        canvas.drawCircle(w - 12f * density, 12f * density, r, paint)
    }

    private fun formatRingSubFiveHour(resetsAt: Instant?): String {
        if (resetsAt == null) return "all models\nresets soon"
        val now = Instant.now()
        val time = resetsAt.atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("HH:mm"))
        return if (Duration.between(now, resetsAt).toHours() < 24) {
            "all models\nresets $time"
        } else {
            val day = resetsAt.atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("EEE d MMM", Locale.getDefault()))
            "all models\nresets $day"
        }
    }

    private fun formatRingSubSevenDay(resetsAt: Instant?): String {
        if (resetsAt == null) return "resets\nlater"
        val day = resetsAt.atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("EEE d MMM", Locale.getDefault()))
        return "resets\n$day"
    }

    private fun formatCountdown(resetsAt: Instant?): String {
        if (resetsAt == null) return "—"
        val now = Instant.now()
        if (resetsAt.isBefore(now)) return "now"
        val duration = Duration.between(now, resetsAt)
        val hours = duration.toHours()
        val minutes = (duration.toMinutes() % 60)
        return when {
            hours <= 0 -> "${minutes}m"
            hours >= 24 -> "${hours / 24}d ${hours % 24}h"
            else -> "${hours}h ${minutes}m"
        }
    }
}
