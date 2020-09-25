Version
=======

0.6

Downloads
=========

These softwares are stored in the static directory. This is just a reminder on
where they have been taken and what are the versions used here :

- `JQuery <https://code.jquery.com/jquery/>`_ - Version 3.5.1 ;
- `Bootstrap 4 <http://getbootstrap.com/>`_ - Version 4.5.2 ;
- `Popper <https://popper.js.org/>`_- Version 2.5.1 ;
- `Moment <https://momentjs.com/>`_- Version 2.29.0 ;
- `Tempus Dominus - Bootstrap 4 <htpp://>`_ - Version 5.1.2 ;
- `Font Awesome <https://fontawesome.com/>`_- Version 5.14.0 ;

Internationalization
====================

Creation : ::

    pybabel extract -F babel-mapping.ini -k _ -k _l --no-wrap -o locales/messages.pot .
    pybabel init -i messages.pot -d translations -l en
    pybabel init -i messages.pot -d translations -l fr
    pybabel compile -d translations

Update : ::

    pybabel extract -F babel-mapping.ini -k _ -k _l --no-wrap -o locales/messages.pot .
    pybabel update -i messages.pot --no-wrap -d translations
    pybabel compile -d translations


Note
====

I use the github version of aiohttp-babel because I use a feature that is not
included in the latest release.
