## Publishing OpenAPI Scripts

#### Doc

Click here from info[https://confluence.unity3d.com/pages/viewpage.action?pageId=176105065]

#### How to run

1. Install Python 3.7
2. `pip install -r requirements.txt`
3. Complete `config.json`, fill in username and password, set host to the assetstore url of corresponding environment
4. `python publishing.py --action ACTION [--name NAME] [--version VERSION] [--package PACKAGE]`
   1. ACTION "**save**": Should also give argument NAME, representing json format package data `/packages/NAME.json`. This action will create or update the package regarding key "packageId" in json. The submission will be also triggered if key "submission" is given in the json.
   2. ACTION "**submit**": Should also give argument NAME. This action requires key "packageId" and "submission" in json.
   3. ACTION "**saveall**": This action executes action "save" for all package data under `/packages`. It will generate a log file named with current timestamp.
   4. ACTION "**package**": Should also give argument PACKAGE. This action returns the package data with given id.
   5. ACTION "**version**": Should also give argument VERSION. This action returns the package version data with given id.
   6. ACTION "**delete**": Should also give argument VERSION. This action will delete draft version with given id.
   7. ACTION "**deprecate**": Should also give argument PACKAGE. This action will deprecate published version of given package.
   8. ACTION "**launch**": Should also give argument PACKAGES, DISCOUNT, DURATION. This action will setup launch discount for given packages with given discount and duration. Note only never published packages can take this action. Available discount choices are 0, 10, 30, 50, available duration choices are 0, 7, 14.
   9. ACTION "**categories**": This action will list all available categories.
   10. ACTION "**unity**": This action will list all available unity versions.
   11. ACTION "**limit**": This action will show the limitations of current publisher.
5. To modify the script in your own way, please visit https://publisher.unity.com/open-api for more information.

#### Fields of `/packages/NAME.json`

1. packageId: Determines creating or updating of action "save", will be automatically filled once package is created. Also required for action "submit".
2. versionName
3. price: 0 or value not less than 4.99
4. category: Must be one of category in categories listed by action "categories"
5. metadatas: A map with language code as key. Accepted language codes include: en_US, zh_CN, ko_KR, ja_JP. A value in the map contains following fields: name, releaseNotes, summary, technicalDetails, description, compatibilityInfo.
6. tags: A list of 3 to 15 tags
7. artworks: List of objects with "type" and "source" in each object. Accepted types include: screenshot, audio, video, youtube, vimeo, soundcloud, mixcloud, sketchfab. For type screenshot, audio or video, field source is the local file location. For other types, field source is the url of media.
8. keyImages: A map with key image type as key and local file location as value. Accepted key image types include: icon, card, cover and social media. The size of each image types are: icon - 160×160, card - 420×280, cover - 1950×1300, social_media - 1200×630.
9. unitypackages: A map with unity version as key. A value in the map contains following fields: source, slices, threads, alwaysUpload, srps, dependencies. If "source" (local file location) is given, the unitypackage will be uploaded. If "alwaysUpload" is set to true or the size of local file is different from the remote file, the upload will be launched. The upload will be executed according to argument "slices" (max 32 slices and max 500MB per slice) and "threads". Extra disk space for unitypackage slices will be occupied during the upload process.
10. submissions: A map with following fields: submitMessage, autoPublish, acceptLatestTerms.

#### API limitations of publisher

1. maxApiCallsPerDay
2. unitypackageUploadThreads
3. packageCreationsTotal
4. packageCreationsPerDay
5. submissionsAndDeletionsTotal
6. submissionsAndDeletionsPerDay
7. remainingApiCallsToday
8. remainingUnitypackageUploadThreads
9. remainingPackageCreationsTotal
10. remainingPackageCreationsToday
11. remainingSubmissionsAndDeletionsTotal
12. remainingSubmissionsAndDeletionsToday

If you want to enhance any limitations, please contact our support.
