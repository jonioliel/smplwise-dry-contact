# פרסום SMPLwise Dry Contact ב־GitHub וב־HACS

שם המאגר: **`smplwise-dry-contact`**.

שם האינטגרציה ב־Home Assistant וב־HACS: **SMPLwise Dry Contact**.

תיאור להדבקה ב־GitHub:

```text
Local Home Assistant integration for EBYTE M31 / M31-U digital and analog IO by SMPLwise
```

## 1. יצירת המאגר

פתח את [יצירת מאגר חדש ב־GitHub](https://github.com/new), בחר את המשתמש או הארגון שלך, הזן את שם המאגר והתיאור ובחר **Public**. השאר את אפשרויות יצירת README, רישיון ו־gitignore כבויות, כי הקבצים מוכנים בפרויקט. לאחר מכן לחץ **Create repository**.

מומלץ להוסיף תחת About את הנושאים: `home-assistant`, `hacs`, `custom-integration`, `modbus`, `ebyte`, `dry-contact`, `smplwise`. השאר את Issues פעיל כדי לאפשר דיווח תקלות.

## 2. התאמת פרטי המאגר

אם כבר מסרת בצ׳אט את קישור המאגר והקבצים עודכנו בהתאם, דלג על שלב זה. אחרת, החלף את `OWNER` בשם המשתמש האמיתי שלך והריץ מתוך תיקיית הפרויקט:

```powershell
python tools/configure_repository.py https://github.com/OWNER/smplwise-dry-contact
python tools/validate_repository.py
```

הפקודה מעדכנת את `codeowners`, קישורי התיעוד ודיווח התקלות ואת קישורי README. אם המאגר שייך לארגון, ניתן להוסיף `--maintainer USERNAME` עם שם המשתמש של המתחזק בפועל.

## 3. העלאת הקבצים

אפשר להעלות דרך ממשק GitHub: חלץ את `smplwise-dry-contact-source.zip`, בחר **uploading an existing file** או **Add file → Upload files**, וגרור את תוכן החבילה לשורש המאגר. העלה את הקבצים והתיקיות שחולצו, כולל `.github`, ולא את קובץ ה־ZIP עצמו. ודא ש־`hacs.json` ו־`README.md` נמצאים בשורש ושקיים `custom_components/ebyte_m31/manifest.json`.

אם אתה משתמש ב־Git מקומי, אלה הפקודות מתוך תיקיית הפרויקט; החלף את `OWNER` לפני ההרצה:

```powershell
git init -b main
git add .
git commit -m "Prepare SMPLwise Dry Contact for HACS"
git remote add origin https://github.com/OWNER/smplwise-dry-contact.git
git push -u origin main
```

אם Git כבר אותחל, אין צורך להריץ שוב `git init`. אם כבר קיים commit ראשוני, אפשר לדלג גם על `git add` ו־`git commit` כל עוד לא שינית קבצים מאז. אם Git מבקש שם ודוא״ל, הגדר את הזהות האישית שלך; אל תשתמש בערכים של אדם אחר. כניסה לחשבון GitHub עשויה להידרש בעת ה־push.

## 4. בדיקות וגרסה

במאגר GitHub פתח **Actions → Validate** ובדוק שהבדיקות עברו. הבדיקות כוללות HACS, Hassfest ובדיקות Python. אלה בדיקות בענן; הבדיקות המקומיות אינן מאשרות שעברו.

לאחר מכן בחר **Releases → Draft a new release**. צור תגית **`v1.2.0`** ופרסם גרסה בשם **SMPLwise Dry Contact 1.2.0**. מספר הגרסה צריך להתאים לשדה `version` ב־`manifest.json`. אפשר לצרף את קובץ ההתקנה הידני `smplwise-dry-contact-1.2.0.zip`, אך HACS מוגדר כאן לקרוא את קובצי האינטגרציה מהמאגר עצמו, ללא תלות בקובץ המצורף.

פרסום Release מומלץ לקבלת מספרי גרסה ברורים. אפשר להוסיף ל־HACS גם מאגר תקין ללא Release; במקרה כזה הוא קורא מהענף המוגדר כברירת מחדל.

## 5. התקנה ב־HACS

1. ב־Home Assistant פתח **HACS**.
2. בתפריט שלוש הנקודות בחר **Custom repositories**.
3. הדבק `https://github.com/OWNER/smplwise-dry-contact` ובחר **Integration**.
4. לחץ **Add** וחפש **SMPLwise Dry Contact**.
5. הורד את האינטגרציה והפעל מחדש את Home Assistant.
6. עבור אל **הגדרות → מכשירים ושירותים → הוסף אינטגרציה → SMPLwise Dry Contact** והזן את כתובת הבקר.

זהו מאגר מותאם אישית ב־HACS. כדי להופיע בקטלוג ברירת המחדל נדרשת הגשה נפרדת ל־HACS ואישור שלהם; אין צורך בכך להתקנה בדרך המתוארת כאן.

## עדכון גרסאות בעתיד

עדכן את שדה `version` ב־`custom_components/ebyte_m31/manifest.json`, העלה את השינוי ופרסם Release עם תגית תואמת. אם יצרת בעבר את ZIP המקור, צור אותו מחדש לפני כל העלאה ידנית כדי שיכלול את הגרסה ופרטי המאגר המעודכנים:

```text
python tools/build_release.py
```

מקורות: [דרישות פרסום HACS](https://www.hacs.xyz/docs/publish/start/), [מבנה מאגר אינטגרציה](https://www.hacs.xyz/docs/publish/integration/), [הוספת מאגר מותאם אישית](https://www.hacs.xyz/docs/faq/custom_repositories/).
