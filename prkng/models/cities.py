from prkng.database import db

import aniso8601


class City(object):
    """
    A class to manage interaction with different cities that the app serves (also referred to as `service areas`).
    """

    @staticmethod
    def get(x, y):
        """
        Get the current city based on location data.

        :param x: longitude (int)
        :param y: latitude (int)
        :returns: name of current city (str)
        """
        city = db.engine.execute("""
            SELECT name FROM cities
            WHERE ST_Intersects(geom, ST_Buffer(ST_Transform('SRID=4326;POINT({x} {y})'::geometry, 3857), 3))
        """.format(x=x, y=y)).first()
        return city[0] if city else None

    @staticmethod
    def get_all():
        """
        Get all cities that we currently service.
        A city object contains its `name`, `display_name`, the `lat` and `long` of its map center (i.e. the default point at which the map opens on app load), and a rough approximation of the `urban_area_radius`.

        :returns: list of City objects (dicts)
        """
        res = db.engine.execute("""
            SELECT
                gid AS id,
                name,
                name_disp AS display_name,
                lat,
                long,
                ua_rad AS urban_area_radius
            FROM cities
        """).fetchall()

        return [{key: value for key, value in row.items()} for row in res]

    @staticmethod
    def get_assets():
        """
        Obtain all links for city polygon masks (map statics).

        :returns: list of City asset objects (dicts)
        """
        res = db.engine.execute("""
            SELECT
                version,
                kml_addr,
                geojson_addr,
                kml_mask_addr,
                geojson_mask_addr
            FROM city_assets
        """).fetchall()

        return [
            {key: value for key, value in row.items()}
            for row in res
        ]

    @staticmethod
    def get_permits(city, residential=False):
        """
        Get all parking permits found within a specific city.
        A Permit object includes the `city` in question, as well as the `permit` name/number, and if it is `residential` or not.

        :param city: city name (str)
        :param residential: True to exclude commercial parking permits (bool)
        :returns: list of Permit objects (dicts)
        """
        res = "SELECT * FROM permits WHERE city = '{city}'"
        if residential:
            res += " AND residential = true"

        res = db.engine.execute(res.format(city=city)).fetchall()
        return [
            {key: value for key, value in row.items()}
            for row in res
        ]

    @staticmethod
    def get_checkins(city, start, end):
        """
        Get all checkins in a city within a certain period.
        Used for Admin interface only.

        :param city: city name (str)
        :param start: start time to filter from (ISO-8601 str)
        :param end: end time to filter to (ISO-8601 str)
        :returns: list of Checkin objects (obj)
        """
        res = db.engine.execute("""
            SELECT
                c.id,
                c.user_id,
                c.slot_id,
                s.way_name,
                to_char(c.checkin_time, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS checkin_time,
                to_char(c.checkout_time, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS checkout_time,
                u.name,
                u.email,
                u.gender,
                c.long,
                c.lat,
                c.checkout_time IS NULL AS active,
                a.auth_type AS user_type,
                COALESCE(s.rules, '[]'::jsonb) AS rules
            FROM checkins c
            LEFT JOIN slots s ON s.id = c.slot_id
            JOIN users u ON c.user_id = u.id
            JOIN cities ct ON (ST_intersects(s.geom, ct.geom)
                OR ST_intersects(ST_transform(ST_SetSRID(ST_MakePoint(c.long, c.lat), 4326), 3857), ct.geom))
            JOIN
                (SELECT auth_type, user_id, max(id) AS id
                    FROM users_auth GROUP BY auth_type, user_id) a
                ON c.user_id = a.user_id
            WHERE ct.name = '{}'
            {}
            """.format(city,
                ((" AND (c.checkin_time AT TIME ZONE 'UTC') >= '{}'".format(aniso8601.parse_datetime(start).strftime("%Y-%m-%d %H:%M:%S"))) if start else "") +
                ((" AND (c.checkin_time AT TIME ZONE 'UTC') <= '{}'".format(aniso8601.parse_datetime(end).strftime("%Y-%m-%d %H:%M:%S"))) if end else "")
            )).fetchall()

        return [
            {key: value for key, value in row.items()}
            for row in res
        ]

    @staticmethod
    def get_reports(city):
        """
        Get all reports made in a city.
        Used for Admin interface only.

        :param city: city name (str)
        :returns: list of Report objects (obj)
        """
        res = db.engine.execute("""
            SELECT
                r.id,
                to_char(r.created, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created,
                r.slot_id,
                u.id AS user_id,
                u.name AS user_name,
                u.email AS user_email,
                s.way_name,
                s.rules,
                r.long,
                r.lat,
                r.image_url,
                r.notes,
                r.progress,
                ARRAY_REMOVE(ARRAY_AGG(c.id), NULL) AS corrections
            FROM reports r
            JOIN cities ct ON ST_intersects(ST_transform(ST_SetSRID(ST_MakePoint(r.long, r.lat), 4326), 3857), ct.geom)
            JOIN users u ON r.user_id = u.id
            LEFT JOIN slots s ON r.slot_id = s.id
            LEFT JOIN corrections c ON s.signposts = c.signposts
            WHERE ct.name = '{}'
            GROUP BY r.id, u.id, s.way_name, s.rules
            """.format(city)).fetchall()

        return [
            {key: value for key, value in row.items()}
            for row in res
        ]

    @staticmethod
    def get_corrections(city):
        """
        Get all report corrections made in a city.
        Used for Admin interface only.

        :param city: city name (str)
        :returns: list of Correction objects (obj)
        """
        res = db.engine.execute("""
            SELECT
                c.*,
                s.id AS slot_id,
                s.way_name,
                s.button_location ->> 'lat' AS lat,
                s.button_location ->> 'long' AS long,
                c.code = ANY(ARRAY_AGG(codes->>'code')) AS active
            FROM corrections c,
                slots s,
                jsonb_array_elements(s.rules) codes
            WHERE c.city = '{}'
                AND c.signposts = s.signposts
            GROUP BY c.id, s.id
        """.format(city)).fetchall()

        return [
            {key: value for key, value in row.items()}
            for row in res
        ]
