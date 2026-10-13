/* Permission editor — alman dili (de) etiketləri.
 *
 * 2026-10-13 (gecə): alman dili əlavə olundu. `labels.js` 600 sətir həddinə yaxın olduğu üçün
 * «de» blokları ayrıca faylda saxlanılır və `labels.js`-dən ƏVVƏL yüklənir; `labels.js`
 * `ns.extraLabelLanguages`-dəki dilləri öz cədvəllərinə qoşur (az/en/ru/tr kimi).
 */
(function (ns) {
    "use strict";

    ns.extraLabelLanguages = ns.extraLabelLanguages || {};
    ns.extraLabelLanguages.de = {
        moduleLabels: {
            org: "Organisation",
            unit: "Struktur",
            member: "Mitglieder",
            role: "Rollen",
            course: "Kurse",
            assignment: "Aufgaben",
            project: "Kursarbeiten",
            lab: "Laborarbeiten",
            grade: "Bewertung",
            journal: "Journal",
            syllabus: "Syllabus",
            group: "Gruppen",
            exam: "Prüfungen",
            appeal: "Einsprüche",
            analytics: "Analytik",
            qa: "Qualität",
            audit: "Audit",
            people: "Verzeichnis der Lehrkräfte und Studierenden",
            system: "Systemüberwachung"
        },
        moduleSubtitles: {
            organization: "Organisationseinstellungen und Verwaltungsvorgänge",
            structure: "Fakultäten, Lehrstühle und Struktureinheiten",
            members: "Vorgänge zu Benutzern und Mitgliedschaften",
            roles: "Rollenzuweisung und Rollenstufen",
            courses: "Kurserstellung und Kursverwaltung",
            grading: "Bewertungs- und Ergebnisabläufe",
            journal: "Journalzugriff und dokumentierte Korrekturen",
            syllabus: "Erstellung, Genehmigung und Versionierung des Syllabus",
            groups: "Erstellung und Verwaltung von Studierendengruppen",
            exams: "Prüfungsverwaltung und Überwachung",
            appeal: "Einspruchsanträge",
            analytics: "Analytische Berichte und Kennzahlen",
            qa: "Vorgänge der Qualitätssicherung",
            audit: "Verlauf und Zugriff auf das Audit-Protokoll"
        },
        actionWordMap: {
            view: "Anzeigen",
            list: "Liste",
            create: "Erstellen",
            edit: "Bearbeiten",
            update: "Aktualisieren",
            delete: "Löschen",
            settings: "Einstellungen",
            manage: "Verwalten",
            correct: "Korrigieren",
            assign: "Zuweisen",
            revoke: "Entziehen",
            approve: "Genehmigen",
            reject: "Ablehnen",
            submit: "Zur Genehmigung einreichen",
            review: "Prüfwarteschlange",
            revise: "Zur Überarbeitung zurückgeben",
            export: "Exportieren",
            import: "Importieren",
            publish: "Veröffentlichen",
            archive: "Archivieren",
            permissions: "Berechtigungen",
            permission: "Berechtigung",
            members: "Mitglieder",
            role: "Rolle",
            roles: "Rollen",
            grades: "Noten",
            grade: "Note",
            exam: "Prüfung",
            exams: "Prüfungen",
            analytics: "Analytik",
            audit: "Audit"
        },
        uiText: {
            guideTitle: "Wofür ist dieser Bereich?",
            guideText: "Hier legen Sie fest, welche Funktionen für diese Rolle freigeschaltet sind.",
            guideSteps: [
                "Öffnen Sie einen Bereich (z. B. Organisation, Mitglieder)",
                "Mit „Hinzufügen“ aktivieren, mit „Entfernen“ deaktivieren",
                "Für mehrere Berechtigungen Kontrollkästchen und Sammelschaltflächen verwenden"
            ],
            legendActive: "Aktiv: Die Berechtigung ist freigeschaltet, die Funktion ist nutzbar.",
            legendInactive: "Inaktiv: Die Berechtigung ist gesperrt, die Funktion ist eingeschränkt.",
            legendBulk: "Sammelaktion: ändert mehrere Berechtigungen gleichzeitig.",
            allPermissionsBadge: "Alle Berechtigungen (*)",
            allPermissionsDescription: "Für diese Rolle sind alle Berechtigungen aktiv.",
            statusActive: "Aktiv",
            statusInactive: "Inaktiv",
            actionAdd: "Hinzufügen",
            actionRemove: "Entfernen",
            searchPlaceholder: "Berechtigung suchen (z. B. view, edit, member)",
            searchButton: "Suchen",
            emptyResults: "Keine Ergebnisse gefunden.",
            activeCount: "Aktive Berechtigungen: {count}",
            toolbarSelectAll: "Alle auswählen",
            toolbarDeselectAll: "Auswahl aufheben",
            toolbarBulkAdd: "Ausgewählte hinzufügen",
            toolbarBulkRemove: "Ausgewählte entfernen",
            genericAction: "Aktion",
            moduleSubtitleFallback: "Berechtigungen für diesen Bereich"
        },
        describe: function (moduleLabel, actionLabel) {
            return "Erlaubt die Aktion „" + actionLabel + "“ im Bereich „" + moduleLabel + "“.";
        }
    };
})(window.EMSPermissionEditor = window.EMSPermissionEditor || {});
