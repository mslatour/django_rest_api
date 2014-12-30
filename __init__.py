"""Django REST API"""
from django.conf.urls import url, include

class RESTAPI(object):
    """Dispatcher object for RESTView's."""

    view_by_model = {}
    name_by_model = {}
    urls = []

    @staticmethod
    def register(Model, View, name=None):
        """Register ```View``` to serve an API for ```Model```."""
        if name is None:
            name = Model._meta.verbose_name_plural.lower().replace(' ','')
        RESTAPI.view_by_model[Model] = View
        RESTAPI.name_by_model[Model] = name
        RESTAPI.urls.append(url(r'^%s' % (name,), include(View.urls(),
            namespace='api_%s' % (name,))))

    @staticmethod
    def get_view_by_model(Model):
        """Get the view class that is registered for ```Model```."""
        if Model in RESTAPI.view_by_model:
            return RESTAPI.view_by_model[Model]
        else:
            for Base in Model.__bases__:
                view = RESTAPI.get_view_by_model(Base)
                if view is not None:
                    return view
        return None

    @staticmethod
    def get_name_by_model(Model):
        """Get the name that is registered for ```Model```."""
        if Model in RESTAPI.name_by_model:
            return RESTAPI.name_by_model[Model]
        else:
            for Base in Model.__bases__:
                view = RESTAPI.get_name_by_model(Base)
                if view is not None:
                    return view
        return None
