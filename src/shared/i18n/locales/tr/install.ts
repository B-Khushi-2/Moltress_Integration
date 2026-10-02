export default {
  preparing: "Hazırlanıyor...",
  startingInstall: "Kurulum başlatılıyor",
  installationComplete: "Kurulum Tamamlandı",
  installationFailed: "Kurulum Başarısız",
  installingMoltress: "Moltress Agent Kuruluyor",
  installationFailedHint:
    "Kurulum başarısız oldu. Lütfen tekrar deneyin veya terminal üzerinden kurun.",
  retryInstallation: "Kurulumu Tekrar Dene",
  copied: "Kopyalandı!",
  copyLogs: "Günlükleri Kopyala",
  stepLabel: "Adım {{step}}/{{total}}: {{title}}",
  waitingToStart: "Başlamayı bekliyor...",
  continueToSetup: "Kuruluma Devam Et",
  confirmTitle: "Kurmadan Önce",
  confirmLocationLabel: "Moltress şuraya kurulacak:",
  confirmFresh:
    "Burada mevcut bir kurulum bulunamadı — yeni bir kopya oluşturulacak.",
  confirmUpdate:
    "Burada mevcut bir Moltress kurulumu var — en son sürüme güncellenecek.",
  confirmReplace:
    "Burada bir klasör var ancak geçerli bir Moltress kurulumu değil — kurulum bu klasörü silip yenisiyle değiştirecektir.",
  confirmNotInherited:
    "Moltress'i başka bir yere veya komut satırından kurduysanız, buraya taşınmayacaktır.",
  confirmInstallBtn: "Moltress'i Kur",
  useExistingBtn: "Mevcut bir kurulumu kullan",
  useExistingHint:
    "Mevcut Moltress kurulumunuzu içeren klasörü seçin (moltress-agent klasörünü içeren).",
  useExistingInvalid:
    "Bu klasörde kullanılabilir bir Moltress kurulumu bulunamadı.",
  useExistingDone:
    "Mevcut kurulum ayarlandı — uygulamak için Moltress'i kapatıp yeniden açın.",
  useExistingQuitBtn: "Moltress'ten Çık",
} as const;
