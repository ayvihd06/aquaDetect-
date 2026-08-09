import subprocess
import sys


# =========================================================
# TAMIL NADU DISTRICTS
# =========================================================

DISTRICTS = [
    ("Ariyalur", 11.1401, 79.0786),
    ("Chennai", 13.0827, 80.2707),
    ("Coimbatore", 11.0168, 76.9558),
    ("Cuddalore", 11.7480, 79.7714),
    ("Dharmapuri", 12.1211, 78.1582),
    ("Dindigul", 10.3673, 77.9803),
    ("Erode", 11.3410, 77.7172),
    ("Kancheepuram", 12.8342, 79.7036),
    ("Kanniyakumari", 8.0883, 77.5385),
    ("Karur", 10.9601, 78.0766),
    ("Madurai", 9.9252, 78.1198),
    ("Nagapattinam", 10.7672, 79.8449),
    ("Namakkal", 11.2194, 78.1677),
    ("Nilgiris", 11.4064, 76.6932),
    ("Perambalur", 11.2333, 78.8833),
    ("Pudukkottai", 10.3833, 78.8001),
    ("Ramanathapuram", 9.3639, 78.8395),
    ("Salem", 11.6643, 78.1460),
    ("Sivaganga", 9.8433, 78.4809),
    ("Thanjavur", 10.7867, 79.1378),
    ("Theni", 10.0104, 77.4768),
    ("Thiruvallur", 13.1439, 79.9080),
    ("Thoothukudi", 8.7642, 78.1348),
    ("Tiruchirappalli", 10.7905, 78.7047),
    ("Tirunelveli", 8.7139, 77.7567),
    ("Tiruvannamalai", 12.2253, 79.0747),
    ("Vellore", 12.9165, 79.1325),
    ("Villupuram", 11.9401, 79.4861),
    ("Virudhunagar", 9.5851, 77.9579),
]


# =========================================================
# ALREADY COMPLETED
# =========================================================

COMPLETED = {
    "madurai",
    "chennai",
    "coimbatore",
    "salem",
}


# =========================================================
# PROCESS DISTRICTS
# =========================================================

total = len(DISTRICTS)

completed_count = 0
skipped_count = 0
failed = []


for index, (district, latitude, longitude) in enumerate(
    DISTRICTS,
    start=1
):

    district_key = district.lower()

    print()
    print("=" * 70)
    print(
        f"[{index}/{total}] {district}"
    )
    print("=" * 70)


    # -----------------------------------------------------
    # Skip already completed districts
    # -----------------------------------------------------

    if district_key in COMPLETED:

        print(
            f"Skipping {district} - already completed."
        )

        skipped_count += 1

        continue


    # -----------------------------------------------------
    # Generate district
    # -----------------------------------------------------

    command = [
        sys.executable,
        "generate_district.py",
        district,
        str(latitude),
        str(longitude),
    ]


    try:

        result = subprocess.run(
            command
        )


    except Exception as error:

        print()
        print(
            f"ERROR starting {district}:"
        )

        print(error)

        failed.append(
            district
        )

        continue


    # -----------------------------------------------------
    # Check result
    # -----------------------------------------------------

    if result.returncode == 0:

        print()
        print(
            f"SUCCESS: {district}"
        )

        completed_count += 1

    else:

        print()
        print(
            f"FAILED: {district}"
        )

        failed.append(
            district
        )


# =========================================================
# FINAL SUMMARY
# =========================================================

print()
print("=" * 70)
print("TAMIL NADU DISTRICT PROCESSING SUMMARY")
print("=" * 70)

print(
    "Total districts:",
    total
)

print(
    "Newly completed:",
    completed_count
)

print(
    "Already completed:",
    skipped_count
)

print(
    "Failed:",
    len(failed)
)


if failed:

    print()
    print("Failed districts:")

    for district in failed:

        print(
            "-",
            district
        )

else:

    print()
    print(
        "All requested districts completed successfully!"
    )

print()