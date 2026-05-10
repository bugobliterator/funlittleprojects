-keep class com.sidbh.claudeusage.data.** { *; }
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt

-keep,includedescriptorclasses class com.sidbh.claudeusage.**$$serializer { *; }
-keepclassmembers class com.sidbh.claudeusage.** {
    *** Companion;
}
-keepclasseswithmembers class com.sidbh.claudeusage.** {
    kotlinx.serialization.KSerializer serializer(...);
}
